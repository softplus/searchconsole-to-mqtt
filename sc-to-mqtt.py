#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Send Search Console Clicks, Impressions to MQTT
#
# John Mueller
# SPDX-License-Identifier: Apache-2.0
#
# Prerequisites:
# paho mqtt - https://pypi.org/project/paho-mqtt/
#  pip3 install paho-mqtt
# Google APIs - https://developers.google.com/webmaster-tools/search-console-api-original/v3/quickstart/quickstart-python
#  pip3 install --upgrade google-api-python-client
# client-secrets.json - from Google API
#

from paho.mqtt import client as mqtt_client
from googleapiclient import sample_tools
from configparser import ConfigParser
import json
import random
import datetime
import argparse
import sys
import time

CONFIG_FILE = 'search-to-mqtt.ini'

argparser = argparse.ArgumentParser(add_help=False)
argparser.add_argument('--noconfig', help="Don't send sensor config data", action="store_true")
argparser.add_argument('--remove', help="Remove sensors, don't send data", action="store_true")
argparser.add_argument('--config', default=CONFIG_FILE, help="Configuration file")

def url_to_id(url):
    # Replace cruft from URL to make a MQTT topic ID
    s = url
    s = s.replace("http://", "").replace("https://", "").replace("sc-domain:", "")
    s = s.replace(":", "_").replace(".", "_").replace("/", "")
    return s

# MQTT debug functions
def on_connect(client, userdata, flags, rc):
    print("Connect:   " + str(rc))

def on_message(client, obj, msg):
    print("Message:   " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_log(client, obj, level, string):
    print("Log:       " + string)

def setup_mqtt(config):
    client_id = config.get("config", "client_id")
    client = mqtt_client.Client(client_id)
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_log = on_log
    if config.get("config", "mqtt_username"):
        client.username_pw_set(config.get("config", "mqtt_username"), config.get("config", "mqtt_password"))
    return client


def config_sensors(client, sites, config):
    for site in sites:
        siteid = url_to_id(site)
        siteurl = site
        topicid = config.get("config", "mqtt_prefix") + siteid
        conf = {"state_topic": topicid + "/state"}
        conf.update( { "device": {"name": siteurl, "identifiers": siteurl + "-ID", 
            "manufacturer": "Google", "model": "Search Console" } })
        fields = [["Data age", "age", "hrs"], 
                ["Impressions", "impressions", "x"], 
                ["Clicks", "clicks", "x"]]
        for f in fields:
            conf.update( {"name": f[0], 
                "unit_of_measurement": f[2], 
                "value_template": "{{ value_json." + f[1] + "}}", 
                "unique_id": siteid + f[1]})
            client.publish(topicid + f[1] + "/config", json.dumps(conf))



def do_it(service, config, sites, configure_mqtt=True, remove_sensors=False):
    client = setup_mqtt(config)
    client.connect(config.get("config", "mqtt_broker"), int(config.get("config", "mqtt_port")))
    if remove_sensors:
        print("Removing sensors...")
        for site in sites:
            siteid = url_to_id(site)
            for sensor in ["clicks", "impressions", "age", "imps", "clx"]:
                client.publish(config.get("config", "mqtt_prefix") + siteid + sensor + "/config", "")
            client.publish(config.get("config", "mqtt_prefix") + siteid + "/config", "")
        return
    if configure_mqtt: config_sensors(client, sites, config)

    # request data from last 7 days; use last entry
    start_date = (datetime.datetime.utcnow() + datetime.timedelta(days=-7)).strftime("%Y-%m-%d")
    end_date = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # get last datapoint dates
    request = {
      'startDate': start_date, 'endDate': end_date,
      'dimensions': ['date'], 'dataState': 'all'
    }

    for site in sites:
        print("Processing ", site)
        response = service.searchanalytics().query(siteUrl=site, body=request).execute()

        if "rows" in response:
            row = response["rows"][-1]
            print("Data row: ", row)
            fresh_date = row["keys"][0]

            section_name = site
            if not config.has_section(section_name): config.add_section(section_name)

            data_age = (datetime.datetime.utcnow() - 
                datetime.datetime.strptime(fresh_date, '%Y-%m-%d'))
            data_age_hrs = round(data_age.days*24 + data_age.seconds/(60*60), 1)

            data = {"impressions": row["impressions"], "clicks": row["clicks"], "age": data_age_hrs}
            topicid = config.get("config", "mqtt_prefix") + url_to_id(site)
            client.publish(topicid + '/state', json.dumps(data))

            config.set(section_name, "last_row", json.dumps(row))
            config.set(section_name, "last_run", datetime.datetime.utcnow().isoformat())

def main(argv):
    # connect to SC
    print(datetime.datetime.utcnow().isoformat(), " - ", __file__)

    service, flags = sample_tools.init(
        argv, 'searchconsole', 'v1', __doc__, __file__, parents=[argparser],
        scope='https://www.googleapis.com/auth/webmasters.readonly')

    state = ConfigParser()
    state.read(flags.config)

    # settings defaults
    if not state.has_section("config"): state.add_section("config")
    if not state.has_option("config", "mqtt_broker"): state.set("config", "mqtt_broker", "localhost")
    if not state.has_option("config", "mqtt_port"): state.set("config", "mqtt_port", "1883")
    if not state.has_option("config", "mqtt_username"): state.set("config", "mqtt_username", "")
    if not state.has_option("config", "mqtt_password"): state.set("config", "mqtt_password", "")
    if not state.has_option("config", "client_id"): state.set("config", "client_id", "pythonForSeo")
    if not state.has_option("config", "mqtt_prefix"): state.set("config", "mqtt_prefix", "homeassistant/sensor/sc_")
    with open(flags.config, 'w') as configfile: state.write(configfile)

    if not state.has_option("config", "sites"): 
        # Filter for verified websites
        site_list = service.sites().list().execute()
        verified_sites_urls = [s['siteUrl'] for s in site_list['siteEntry']
                            if s['permissionLevel'] != 'siteUnverifiedUser' and s['siteUrl'][:4] == 'http']
        sites = verified_sites_urls[:2] # pick first 2 verified sites to try out
        print("Using these verified sites: ", sites)
        state.set("config", "sites", ", ".join(sites))
        with open(flags.config, 'w') as configfile: state.write(configfile)

    sites = state.get("config", "sites").split(",")
    sites = [x.strip() for x in sites]
    do_it(service, state, sites, configure_mqtt=(not flags.noconfig), remove_sensors=flags.remove)

    with open(flags.config, 'w') as configfile: state.write(configfile)

main(sys.argv)

