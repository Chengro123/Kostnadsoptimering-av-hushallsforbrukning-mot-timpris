This is the result of a bachelor's thesis at Chalmers University of Technology, with the aim of cost-optimizing the electricity consumption of an air heat pump and a water heater against an hourly rate. The implementation takes place in Home Assistant's subsystem AppDaemon. Instructions for applying the optimization code for your air heat pump and/or water heater follows below.

Please note that there might be some swedish left from the original installation. We hope to translate everything to english soon, but untill then two common abbreviations used are LVP for air heat pump or "luftvärmepump" and VVB for water heater or "varmvattenberedare".

# What's needed to start?
- A computer/single-board computer (e.g. Raspberry Pi) to run Home Assistant OS
## What's needed for the water heater?
- A smart plug/some way to control the on/off state of the heater
- Temperature sensors to measure the water temperature on different height in the tank. We used four sensors and put them against the outside of the tank by drilling holes in the surrounding styrofoam.
## What's needed for the air heat pump?
- Some way to control the set temperature for the AHP, we used the swedish invention [Huskoll](https://huskoll.se/).


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
to the top of appdaemon.yaml

and in secrets.yaml add
```yaml
lvp_token: '[yourtoken]'
lvp_hwid: '[yourkey]'
```




To fully make the automation work, data from Nord Pool, inside temperature and weather forecast will be needed. We used WeatherAPI and a REST-sensor to import the forecast to HA. The reason to use a REST-sensor instead of e.g. making an API-call in the code is to reduce calls if the code is ran often.
