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
import datetime
import argparse
import sys

CONFIG_FILE = 'sc-to-mqtt.ini'

argparser = argparse.ArgumentParser(add_help=False)
argparser.add_argument('--noconfig', help="Don't send sensor config data", action="store_true")
argparser.add_argument('--remove', help="Remove sensors, don't send data", action="store_true")
argparser.add_argument('--config', default=CONFIG_FILE, help="Configuration file")
argparser.add_argument('--add7', help="Add data from 7 days ago", action="store_true")

def url_to_id(url):
    # Replace cruft from URL to make a MQTT topic ID
    s = url.replace("http://", "").replace("https://", "").replace("sc-domain:", "")
    s = s.replace(":", "_").replace(".", "_").replace("/", "")
    return s


def connect_mqtt(config):
    # setup & connect to MQTT client
    client_id = config.get("config", "client_id")
    client = mqtt_client.Client(client_id)
    client.on_log  = lambda client,obj,lev,stri : print("MQTT: ", stri)
    if config.get("config", "mqtt_username"):
        client.username_pw_set(config.get("config", "mqtt_username"), 
                               config.get("config", "mqtt_password"))
    client.connect(config.get("config", "mqtt_broker"), 
                   int(config.get("config", "mqtt_port")))
    return client


def config_sensors(client, sites, config, add_7_day):
    # Send sensor info for auto-discovery in Home Assistant
    for site in sites:
        siteid = url_to_id(site)
        siteurl = site
        topicid = config.get("config", "mqtt_prefix") + siteid
        conf = {"state_topic": topicid + "/state"}
        conf.update( { "device": {"name": siteurl, "identifiers": siteurl + "#ID", 
            "manufacturer": "Google", "model": "Search Console" } })
        fields = [["Data age", "age", "hrs"], 
                ["Impressions", "impressions", "x"], 
                ["Clicks", "clicks", "x"]]
        if add_7_day:
            fields.append(["Impressions-7", "impressions7", "x"])
            fields.append(["Clicks-7", "clicks7", "x"])
        for f in fields:
            conf.update( {"name": f[0], 
                "unit_of_measurement": f[2], 
                "value_template": "{{ value_json." + f[1] + "}}", 
                "unique_id": siteid + f[1]})
            client.publish(topicid + f[1] + "/config", json.dumps(conf))


def unconfigure_sensors(config, sites):
    # remove sensors from Home Asssitant setup by sending empty configs
    print("Removing sensors...")
    client = connect_mqtt(config)
    for site in sites:
        siteid = url_to_id(site)
        for sensor in ["clicks", "impressions", "age", "impressions7", "clicks7"]:
            client.publish(config.get("config", "mqtt_prefix") + siteid + sensor + "/config", "")
        client.publish(config.get("config", "mqtt_prefix") + siteid + "/config", "")
        config.set(site, "status", "Unconfigured")
        config.set(site, "status_date", datetime.datetime.utcnow().isoformat())


def do_it(service, config, sites, configure_mqtt=True, add_7_day=True):
    # Connect to MQTT, Get SC data, Send to MQTT
    client = connect_mqtt(config)
    if configure_mqtt: config_sensors(client, sites, config, add_7_day)

    # request data from last 7 days; use last entry
    start_date = (datetime.datetime.utcnow() + datetime.timedelta(days=-7)).strftime("%Y-%m-%d")
    end_date = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    request = { 'startDate': start_date, 'endDate': end_date, 'dimensions': ['date'], 'dataState': 'all' }

    for site in sites:
        response = service.searchanalytics().query(siteUrl=site, body=request).execute()

        if "rows" in response:
            # Get the freshest data, nom nom
            row = response["rows"][-1]

            if not config.has_section(site): config.add_section(site)

            # calculate age in hours (hacky, since we just have a date)
            fresh_date = row["keys"][0]
            data_age = (datetime.datetime.utcnow() - 
                datetime.datetime.strptime(fresh_date, '%Y-%m-%d'))
            data_age_hrs = round(data_age.days*24 + data_age.seconds/(60*60), 1)

            # Create & send MQTT message
            data = {"impressions": row["impressions"], "clicks": row["clicks"], "age": data_age_hrs}
            if add_7_day:
                data["impressions7"] = response["rows"][0]["impressions"]
                data["clicks7"] = response["rows"][0]["clicks"]
            topicid = config.get("config", "mqtt_prefix") + url_to_id(site)
            client.publish(topicid + '/state', json.dumps(data))

            # Log to config file
            config.set(site, "last_row", json.dumps(row))
            config.set(site, "status", "Sent")
            config.set(site, "status_date", datetime.datetime.utcnow().isoformat())


def main(argv):
    # connect to SC, etc
    print(datetime.datetime.utcnow().isoformat(), " - ", __file__, " - started")

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
    with open(flags.config, "w") as configfile: state.write(configfile)

    if not state.has_option("config", "sites"): 
        # Get some verified site URLs
        site_list = service.sites().list().execute()
        verified_sites_urls = [s['siteUrl'] for s in site_list['siteEntry'] if s['permissionLevel'] != 'siteUnverifiedUser']
        sites = verified_sites_urls[:2] # pick first 2 verified sites to try out
        print("Using these verified sites: ", sites)
        state.set("config", "sites", ", ".join(sites))
        with open(flags.config, "w") as configfile: state.write(configfile)

    sites = state.get("config", "sites").split(",")
    sites = [x.strip() for x in sites]

    if flags.remove:
        unconfigure_sensors(state, sites)
    else:
        do_it(service, state, sites, configure_mqtt=(not flags.noconfig), add_7_day=flags.add7)

    with open(flags.config, "w") as configfile: state.write(configfile)
    print(datetime.datetime.utcnow().isoformat(), " - ", __file__, " - done")


if __name__ == '__main__':
    main(sys.argv)
