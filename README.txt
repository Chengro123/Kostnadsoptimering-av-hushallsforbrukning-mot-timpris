Instructions for applying the optimization code for your air heat pump and/or water heater

Insert the code in the folders lvp and vvb into the Appdaemon "apps"-folder in Home Assistant.
To fully make the automation work, data from Nord Pool, inside temperature and weather forecast will be needed. We used WeatherAPI and a REST-sensor to import the forecast to HA. The reason to use a REST-sensor instead of e.g. making an API-call in the code is to reduce calls if the code is ran often.
