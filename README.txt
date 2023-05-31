Instructions for applying the optimization code for your air heat pump and/or water heater

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

and in secrets.yaml:
```yaml
lvp_token: '[yourtoken]'
lvp_hwid: '[yourkey]'
```
To fully make the automation work, data from Nord Pool, inside temperature and weather forecast will be needed. We used WeatherAPI and a REST-sensor to import the forecast to HA. The reason to use a REST-sensor instead of e.g. making an API-call in the code is to reduce calls if the code is ran often.
