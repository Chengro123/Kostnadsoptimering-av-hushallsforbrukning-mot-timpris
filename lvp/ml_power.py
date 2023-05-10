import datetime
import numpy as np
import adbase as ad
import hassapi as hass
import json

class calculatePower(hass.Hass, ad.ADBase):
    def initialize(self):
        self.adapi = self.get_ad_api()
        self.adapi.run_hourly(self.main, datetime.time(0, 1, 0))
        #self.adapi.run_minutely(self.main, datetime.time(0, 13, 0))

    def main(self, ignore=0):
        now = datetime.datetime.now()

        # Get how many kWh that were used last hour 
        self.pwr_id = 'sensor.shelly_em3_channel_a_energy'
        data = self.get_history(entity_id=self.pwr_id, start_time=now-datetime.timedelta(hours = 1))
        usedPower = float(data[0][-1]['state']) - float(data[0][0]['state'])

        # Get average inside temperature under last hour
        self.t_in_id = 'sensor.temp_average_inside'
        data = self.get_history(entity_id=self.t_in_id, start_time=now-datetime.timedelta(hours = 1))
        t_in = np.mean(np.array([float(hour['state']) for hour in data[0] if not hour['state'] in ('','unknown', 'unavailable')]))

        self.settempfilename = "/config/appdaemon/logs/saved_setpoints.json"
        dateToday = datetime.datetime.now()
        # Open file where settemps and outside temp is saved
        with open(self.settempfilename, "r") as logfile:
            file = json.load(logfile)
            self.settemps    = file["settemps"]
            self.outsideTemp = file["weather"]

        t_set = self.settemps[dateToday.hour-1]['value']
        t_out = self.outsideTemp[dateToday.hour-1]
        dt  = round(t_in-t_out,1)

        settempfilename = "/config/appdaemon/logs/db_settemps.json"

        # Open the database used to store P(t_set, dt)
        with open(settempfilename, 'r') as settempfile:
            database = json.load(settempfile)
            if str(t_set) in database:
                db_t_set = database[str(t_set)]
                i = self.bin(db_t_set["dt"],0,len(db_t_set["dt"])-1,dt)
                if dt in db_t_set["dt"]:
                    prevpwr = db_t_set["power"][i]
                    count = db_t_set["meanCount"][i]
                    db_t_set["power"][i] = (prevpwr+usedPower)/(count+1)
                    db_t_set["meanCount"][i] += 1
                else:
                    db_t_set["dt"].insert(i, dt)
                    db_t_set["power"].insert(i, usedPower)
                    db_t_set["meanCount"].insert(i, 1)
                database[str(t_set)] = db_t_set
            else:
                database[f"{t_set}"] = {"dt"        :[dt],
                                        "power"     :[usedPower],
                                        "meanCount" :[1]
                                        }

        with open(settempfilename, 'w', encoding='utf-8') as databasefile:
            databasefile.write(json.dumps(database, indent=4))

        self.log('ML success, t_set = ' + str(t_set) + ': ' + str({"dt":[dt],"power":[usedPower],"meanCount" :[1]}))

    def bin(self, arr:list, low:float, high:float, x:float) -> int:
        """Binary search, returns index of where the item should been if it not already is in the list."""
        if high >= low: 
            mid = (high + low) // 2
            if arr[mid] == x: return mid
            elif arr[mid] > x: return self.bin(arr, low, mid - 1, x)
            else: return self.bin(arr, mid + 1, high, x)
        else: return low # Element is not present in the array