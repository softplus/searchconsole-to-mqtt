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

