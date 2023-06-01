This is the result of a bachelor's thesis at Chalmers University of Technology, with the aim of cost-optimizing the electricity consumption of an air heat pump and a water heater against an hourly rate. The implementation takes place in Home Assistant's subsystem AppDaemon. Instructions for applying the optimization code for your air heat pump and/or water heater follows below.

Please note that there might be some swedish left from the original installation. We hope to translate everything to english soon, but untill then two common abbreviations used are LVP for air heat pump or "luftvärmepump" and VVB for water heater or "varmvattenberedare".

# What's needed to start?
- A computer/single-board computer (e.g. Raspberry Pi) to run Home Assistant OS with access to the internet.
## What's needed for the water heater?
- A smart plug/some way to control the on/off state of the heater
- Temperature sensors to measure the water temperature on different height in the tank. We used four sensors and put them against the outside of the tank by drilling holes in the surrounding styrofoam.
## What's needed for the air heat pump?
- Some way to control the set temperature for the AHP, we used the swedish invention [Huskoll](https://huskoll.se/).

# Installation
To increase readability and ease of use, we recommend to put all sensor-, input number- and script-configurations in separate files by adding
```yaml
sensor: !include sensors.yaml
input_number: !include input_numbers.yaml
```
in configuration.yaml.

## Nord Pool
Configure the Nord Pool integration and add it to sensors.yaml as
```yaml
- platform: nordpool
  VAT: true
  currency: "SEK"
  region: "SE3"
  precision: 3
  price_type: kWh
```
remember to change the parameters for your location and preferred currency.

## Water heater
In input_numbers.yaml add
```yaml
vvb_test:
  name: vvb status for testing 
  min: 0
  max: 1
```
and in sensors.yaml add
```yaml
- platform: template
  sensors:
    t_vvb_1:
      friendly_name: vvb 1
      value_template: >-
        {% set t_tmp = states('sensor.vvbsensor_1') | float %}
        {{t_tmp+(t_tmp-20)/(45-20)*10}}
      unit_of_measurement: "deg C"
    t_vvb_2:
      friendly_name: vvb 2
      value_template: >-
        {% set t_tmp = states('sensor.vvbsensor_4') | float %}
        {{t_tmp+(t_tmp-20)/(45-20)*10}}
      unit_of_measurement: "deg C"
    t_vvb_3:
      friendly_name: vvb 3
      value_template: >-
        {% set t_tmp = states('sensor.vvbsensor_2') | float %}
        {{t_tmp+(t_tmp-20)/(45-20)*10}}
      unit_of_measurement: "deg C"
    t_vvb_4:
      friendly_name: vvb 4
      value_template: >-
        {% set t_tmp = states('sensor.vvbsensor_3') | float %}
        {{t_tmp+(t_tmp-20)/(45-20)*10}}
      unit_of_measurement: "deg C"
    vvb_energy_to_full:
      friendly_name: Energy to Full
      value_template: >-
        {% set t1 = states('sensor.t_vvb_1') | float %}
        {% set t2 = states('sensor.t_vvb_2') | float %}
        {% set t3 = states('sensor.t_vvb_3') | float %}
        {% set t4 = states('sensor.t_vvb_4') | float %}
        {{ 
        (((max(0,(60-t1)) + max(0,(56-t2)) + max(0,(54-t3)) + max(0,(58-t4))) / 4)*300*4.18/3600)
        }}
      unit_of_measurement: "kWh"
    vvb_soc:
      friendly_name: VVB SOC
      value_template: >-
        {% set t1 = states('sensor.t_vvb_1') | float %}
        {% set t2 = states('sensor.t_vvb_2') | float %}
        {% set t3 = states('sensor.t_vvb_3') | float %}
        {% set t4 = states('sensor.t_vvb_4') | float %}
        {{
        (((max(0, t1-30) + max(0,t2-30) + max(0, t3-30) + max(0, t4-30)) / 4 / (67-30))*100) | round(2)}}
      unit_of_measurement: "percent"
```
Also create three input booleans
```yaml
input_boolean:
  vvb_button1: 
  vvb_button2:
  vvb_model:
```
and two input texts:
```yaml
input_boolean:
  vvb_information1: 
  vvb_information2:
```
Lastly create a .json-file named ```saved_vvb_times.json``` in the logs-folder (full path ```/config/appdaemon/logs/saved_vvb_times.json```). This is where the runtimes for the water heater are saved.

## Air heat pump
Two input booleans
```yaml
input_boolean:
  toggle_lvp_optimizer:
    initial: true
  toggle_include_comftemp:
    initial: true
```
four input numbers
```yaml
mintemp:
   name: Minimum comfort temperature during expensive electricity prices
   initial: 18
   step: 1
   min: 8 # Minimum value that Huskoll allows
   max: 32 # Maximum value that Huskoll allows
maxtemp:
   name: Highest comfort temperature during cheap electricity prices
   initial: 23
   step: 1
   min: 8 # Minimum value that Huskoll allows
   max: 32 # Maximum value that Huskoll allows
comforttemp:
   name: Standard comfort temperature during normal electricity prices
   initial: 20
   step: 1
   min: 8 # Minimum value that Huskoll allows
   max: 32 # Maximum value that Huskoll allows
cooling_constant:
   name: Cooldown constant
   initial: 0.04
   steps: 0.01
   min: 0.01
   max: 0.1
```
and two sensors
```yaml
- platform: rest
  resource: !secret weatherapirestsensorkey
  method: POST
  name: "Weather data via API"
  scan_interval: !secret scanInt
  value_template: "1" # dummy value, not used; avoids the "State max length is 255 characters" error
  json_attributes:
    - "location"
    - "current"
    - "forecast"
  force_update: True
- platform: template
  sensors:
    setpoints:
      friendly_name: The air heat pump's set temperatures
      value_template: "."

```
has to be created, together with the file (```/config/appdaemon/logs/saved_setpoints.json```) to store needed data. The main purpose of this is to avoid crashes if data can not be read from its original source.

## Temperature sensors for the air heat pump
To include temperature sensors in the optimization (recommended), used to measure the inside temperature (preferably some distance away from the air heat pump), follow the steps below.
1. ESPHome
2. YAML för dem
3. YAML för medelvärde
4. MLPOWER

# Configuration
Insert the code in the folders lvp and vvb into the Appdaemon "apps"-folder in Home Assistant. 
Configure the AppDaemon "apps"-file as:
```yaml
lvp_controller:
  module: controlLVP
  class: lvpControl
  log: lvp_control_log
  lvp_token: !secret lvp_token
  lvp_hwid: !secret lvp_hwid
vvb_code:
  module: vvb
  class: VVBCode
  log: vvb_log
mlpower:
  module: ml_power
  class: calculatePower
  log: mlpower_log
```
Remeber to create the log-files and configure them in appdaemon.yaml as e.g.
```yaml
  lvp_control_log:
    name: LVPStyrLogg
    filename: /config/appdaemon/logs/lvp_control.log
```
If secrets is not enabled, add
```yaml
secrets: /config/secrets.yaml
```
to the top of appdaemon.yaml and in secrets.yaml add
```yaml
lvp_token: '[yourtoken]'
lvp_hwid: '[yourkey]'
```

For the water heater, change the variable ```python self.POWER = 3 # kW ``` to correspond to the power your water heater has.


To fully make the automation work, data from Nord Pool, inside temperature and weather forecast will be needed. We used WeatherAPI and a REST-sensor to import the forecast to HA. The reason to use a REST-sensor instead of e.g. making an API-call in the code is to reduce calls if the code is ran often.
