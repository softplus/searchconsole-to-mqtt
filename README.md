# searchconsole-to-mqtt
Publish Search Console API data to MQTT

Want to control your lights based on Google Search impressions of your website?
Or just want fancy graphs of impressions & clicks in your Home Assistant? 

# Setup

## Libraries

PAHO MQTT
https://pypi.org/project/paho-mqtt/

`pip3 install paho-mqtt`

Google APIs
https://developers.google.com/webmaster-tools/search-console-api-original/v3/quickstart/quickstart-python

`pip3 install --upgrade google-api-python-client`

## Google API project & configuration

Follow steps in https://developers.google.com/webmaster-tools/search-console-api-original/v3/quickstart/quickstart-python

Save the `client-secrets.json` file in your local directory.

# Usage

`python3 sc-to-mqtt.py`

On first run, it'll generate a generic `sc-to-mqtt.ini` file for settings. 
You must update this file to make the script work.
It'll also prompt you for Google API authentication. 
Copy the link into a browser, log in, copy the result back here.
The authentication is saved in `searchconsole.dat`.

## Settings required

In `sc-to-mqtt.ini` :

```
[config]
mqtt_broker = mqttbrokerhostname.domain.com
mqtt_port = 1883
mqtt_username = mqttusername
mqtt_password = mqttpassword
client_id = pythonForSeo
mqtt_prefix = homeassistant/sensor/sc_
sites = https://example.com/, https://site.com/
```

mqtt_broker: This is the hostname to your MQTT broker. If you're running it locally, use `localhost`. 

mqtt_port: The default MQTT port is 1833. 

mqtt_username / mqtt_password: If your broker requires authentication, set that here.

client_id: This identifies your client. Change it, leave it, whatever.

mqtt_prefix: This is the prefix used for MQTT topics. 
If you use Home Assistant auto-discovery, make sure it matches your auto-discovery topic prefix. 

sites: The sites to export. They must be verified in Search Console.

## Topics sent

### Sensor configuration for auto-discovery

### Sensor values

