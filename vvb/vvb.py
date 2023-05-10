import yaml
from yaml.loader import SafeLoader
import requests
import hassapi as hass
import numpy as np
import datetime
from math import sqrt
import adbase as ad
import json


class VVBCode(hass.Hass, ad.ADBase):
    def initialize(self):

        self.NORDPOOL_ID = 'sensor.nordpool_kwh_se3_sek_3_10_025' #  

        self.POWER = 3 # 3 kWh
        self.VVB = 'switch.varmvattenberedare' # ID of the real water heater
        self.VVB_TEST = 'input_number.vvb_test' # ID of the fake water heater, for testing
        self.VVB_SOC = 'sensor.vvb_soc' # Id of vvbs state of charge
        self.ENERGY_TO_FULL = 'sensor.vvb_energy_to_full' # Id of vvbs energy to full 

        self.vvb_button1 = 'input_boolean.vvb_knapp1' # Buttons for the water heater window in HA
        self.vvb_button2 = 'input_boolean.vvb_knapp2'
        self.vvb_modell_button = 'input_boolean.vvb_modell' # Button for turning of the model 
        self.vvb_info1 = 'input_text.vvb_information1' 
        self.vvb_info2 = 'input_text.vvb_information2'

        self.vvb_times = "/config/appdaemon/logs/saved_vvb_times.json" # Where the run times are saved

        # When turning on and off the buttons, updates the info text in water heater window 
        self.get_entity(self.vvb_button1).listen_state(self.vvb_info) 
        self.get_entity(self.vvb_button2).listen_state(self.vvb_info)

        
        self.run_hourly(self.vvb_on, datetime.time(hour=14, minute=0, second=0))
        self.run_hourly(self.vvb_off, datetime.time(hour=14, minute=0, second=0))
        self.run_hourly(self.vvb_info, datetime.time(hour=14, minute=0, second=0))

        run_time = datetime.time(hour=17, minute=5, second=0)
        self.run_daily(self.choose_run_time, run_time)
        self.run_daily(self.vvb_info, run_time)

        if self.get_state(self.vvb_modell_button) == 'on':
            self.run_daily(self.button1_on, run_time)
            self.run_daily(self.button2_off, run_time)

        # time = datetime.time(0, 0, 30) # Runs when seconds == 30
        # self.adapi = self.get_ad_api()
        # self.adapi.run_minutely(self.test_runs, time)
        
        #self.vvb_on()
        #self.vvb_off()
        #self.main()
        #self.choose_run_time()
        #self.vvb_info()

    def get_nordpool_price(self):
        nordPoolAPI = self.get_entity(self.NORDPOOL_ID).attributes
        bothRawDays = nordPoolAPI['raw_today'] + nordPoolAPI['raw_tomorrow']
        nordpool = {datetime.datetime.fromisoformat(hour['start']):hour['value'] for hour in bothRawDays}
        return nordpool

    def cheapest_start_time(self, spot_prices, l):
        today = datetime.datetime.now().day
        nighttime = (20,10)
        afternoontime = (10,18)
        prices = list(spot_prices.values())
        hour_prices = list(spot_prices.items())
        run_prices = [(hour_prices[i][0],hour_prices[i+l-1][0] + datetime.timedelta(hours=1), sum(prices[i:i+l])) for i in range(len(prices)-l+1)]
        
        if len(spot_prices) > 24:
            night = sorted([(start,end,cost) for start,end,cost in run_prices if ((20 <= start.hour <= 23 and today == start.day) or (0 <= start.hour <= 10 and today != start.day)) and ((20 <= end.hour <= 23 and today == end.day) or (0 <= end.hour <= 10 and today != end.day))], key = lambda x: x[2])[0]
            afternoon = sorted([(start,end,cost) for start,end,cost in run_prices if (10 <= start.hour <= 18 and today != start.day) and (10 <= end.hour <= 18 and today != end.day)], key = lambda x: x[2])[0]
        
        else: 
            night = sorted([(start,end,cost) for start,end,cost in run_prices if 0 <= start.hour <= 10 and 0 <= end.hour <= 10], key = lambda x: x[2])[0]
            afternoon = sorted([(start,end,cost) for start,end,cost in run_prices if 10 <= start.hour <= 18 and 10 <= end.hour <= 18], key = lambda x: x[2])[0]
        
        cheapest = sorted([night, afternoon], key = lambda x: x[2])
        return cheapest
    
    def writeToFile(self, file:str, data:dict):
        with open(file, 'w', encoding='utf-8') as logfile:
            self.log(f"The dictionary has been written: {data}")
            logfile.write(json.dumps(data, indent=4, cls=DateTimeEncoder))
    
    def readFromFile(self, file:str):
        with open(file, "r") as logfile:
            #self.log("File has been read!")
            return json.load(logfile)

    def choose_run_time(self, ignore = "ignore this"):
        hours_to_run = 3
        current_time = datetime.datetime.now()
        nordpool_prices = self.get_nordpool_price() 
        valid_prices = {time:nordpool_prices[time] for time in nordpool_prices if (time.hour >= current_time.hour and time.day == current_time.day) or (time.day != current_time.day)}
        cheapest = self.cheapest_start_time(valid_prices, hours_to_run)
        c1, c2 = cheapest[0], cheapest[1]
        self.log("this is c1" + str(c1))
        start_time1, end_time1, cost_to_run1 = c1[0], c1[1], c1[2]
        start_time2, end_time2, cost_to_run2 = c2[0], c2[1], c2[2]
        self.writeToFile(self.vvb_times, {
                                        "first": {"start" : start_time1,"end" : end_time1,"cost" : cost_to_run1}, 
                                        "second":{"start" : start_time2,"end" : end_time2,"cost" : cost_to_run2}
                                        })
        self.log('These times have been saved: ' + str({"first": {"start" : start_time1,"end" : end_time1,"cost" : cost_to_run1}, "second":{"start" : start_time2,"end" : end_time2,"cost" : cost_to_run2}}))
    
    def vvb_info(self,a="a",b="b",c="c",d="d",e="e"):

        info = self.readFromFile(self.vvb_times)
        start1 = datetime.datetime.fromisoformat(info["first"]["start"])
        end1 = datetime.datetime.fromisoformat(info["second"]["start"])
        start2 = datetime.datetime.fromisoformat(info["first"]["end"])
        end2 = datetime.datetime.fromisoformat(info["second"]["end"])

        now = datetime.datetime.now()
        date_now = now.date()

        start_date1 = start1.date()
        start_date2 = end1.date()

        start_hour1 = start1.hour
        start_hour2 = end1.hour
        end_hour1 = start2.hour
        end_hour2 = end2.hour

        cost1 = info["first"]["cost"]
        cost2 = info["second"]["cost"]

        if date_now == start_date1:
            dag1 = 'Idag'
        elif date_now + datetime.timedelta(days=1) == start_date1:
            dag1 = 'Imorgon'
        elif date_now - datetime.timedelta(days=1) == start_date1:
            dag1 = 'Igår'
        else:
            dag1 = str(start_date1)

        if date_now == start_date2:
            dag2 = 'Idag'
        elif date_now + datetime.timedelta(days=1) == start_date2:
            dag2 = 'Imorgon'
        elif date_now - datetime.timedelta(days=1) == start_date2:
            dag2 = 'Igår'
        else: 
            dag2 = str(start_date2)

        if start_hour1 < 10: start_hour1 = '0'+str(start_hour1)
        if end_hour1 < 10: end_hour1 = '0'+str(end_hour1)
        if start_hour2 < 10: start_hour2 = '0'+str(start_hour2)
        if end_hour2 < 10: end_hour2 = '0'+str(end_hour2)
        
        self.set_state(self.vvb_button1, attributes={"friendly_name": f"{dag1} från kl. {start_hour1} till {end_hour1} kostar {round(cost1,2)} kr"})
        self.set_state(self.vvb_button2, attributes={"friendly_name": f"{dag2} från kl. {start_hour2} till {end_hour2} kostar {round(cost2,2)} kr"})
        
        self.log("VVB info has been updated")


    def test_runs(self, ignore = "ignore this"):
        self.log("The current state of VVB is: " + self.get_state(self.VVB))
        self.log("The current state of button 1 is: " + self.get_state(self.vvb_button1))
        self.log("The current state of button 2 is: " + self.get_state(self.vvb_button2))
        self.log("The current state modell button is: " + self.get_state(self.vvb_modell_button))
        self.log("The start time is: " + str(datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["start"])))
        self.log("The end time is: " + str(datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["end"])))
        self.log("The start time is: " + str([datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["start"])]))
        self.log("The end time is: " + str([datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["end"])]))
        self.log("Testing stuff")

    def vvb_on(self, ignore = "ignore this"):

        if self.get_state(self.vvb_modell_button) == 'on':
            run_time1 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["start"])
            run_time2 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["second"]["start"])
            now = datetime.datetime.now()
            date_now = now.date()
            hour_now = now.hour

            run_time1_date = run_time1.date()
            run_time1_hour = run_time1.hour
            
            run_time2_date = run_time2.date()
            run_time2_hour = run_time2.hour
            
            self.log("date now: " + str(date_now))
            self.log("hour now: " + str(hour_now))
            self.log("run time 1 date: " + str(run_time1_date))
            self.log("run time 1 hour: " + str(run_time1_hour))
            self.log("run time 2 date: " + str(run_time2_date))
            self.log("run time 2 hour: " + str(run_time2_hour))

            if self.get_state(self.vvb_button1) == 'on' and date_now == run_time1_date and hour_now == run_time1_hour:
                self.turn_on(self.VVB)
                self.set_state(self.VVB_TEST, state="1.0")
                self.log("VVB has been turned on")

            if self.get_state(self.vvb_button2) == 'on'and date_now == run_time2_date and hour_now == run_time2_hour:
                self.turn_on(self.VVB)
                self.set_state(self.VVB_TEST, state="1.0")
                self.log("VVB has been turned on")


    def vvb_off(self, ignore = "just ignore this"):

        end_time1 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["end"])
        end_time2 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["second"]["end"])

        now = datetime.datetime.now()
        date_now = now.date()
        hour_now = now.hour

        end_time1_date = end_time1.date()
        end_time1_hour = end_time1.hour
        
        end_time2_date = end_time2.date()
        end_time2_hour = end_time2.hour

        self.log("date now: "+ str(date_now))
        self.log("hour now: "+ str(hour_now))
        self.log("end time date 1: "+ str(end_time1_date))
        self.log("end time hour 1: "+ str(end_time1_hour))
        self.log("end time date 2: "+ str(end_time2_date))
        self.log("end time hour 2: "+ str(end_time2_hour))

        if self.get_state(self.VVB) == 'on': 
            if (date_now == end_time1_date and hour_now == end_time1_hour) or (date_now == end_time2_date and hour_now == end_time2_hour):
                self.turn_off(self.VVB)
                self.set_state(self.VVB_TEST, state="0.0")
                self.log("VVB has been turned off")
    
    def button1_on(self, ignore = "just ignore this"):
        self.set_state(self.vvb_button1, state="on")
        #self.log("Button 1 has been turned on")

    def button1_off(self, ignore = "just ignore this"):
        self.set_state(self.vvb_button1, state="off")
        #self.log("Button 1 has been turned off")

    def button2_on(self, ignore = "just ignore this"):
        self.set_state(self.vvb_button2, state="on")
        #self.log("Button 2 has been turned on")

    def button2_off(self, ignore = "just ignore this"):
        self.set_state(self.vvb_button2, state="off")
        #self.log("Button 2 has been turned off")



class DateTimeEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()



