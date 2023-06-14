import yaml
from yaml.loader import SafeLoader
import requests
import hassapi as hass
import numpy as np
import datetime
from math import ceil
import adbase as ad
import json
import pytz



class VVBCode(hass.Hass, ad.ADBase):

    def initialize(self):

        self.NORDPOOL_ID = 'sensor.nordpool_kwh_se3_sek_3_10_025' # For getting Nord Pool prices

        self.POWER = 3 # Power of vvb in kW
        self.VVB = 'switch.varmvattenberedare' # Id of the real vvb
        self.ENERGY_TO_FULL = 'sensor.vvb_energy_to_full' # Id of vvb's energy to full 

        self.vvb_button1 = 'input_boolean.vvb_knapp1' # Buttons for the vvb window in HA
        self.vvb_button2 = 'input_boolean.vvb_knapp2' 
        self.vvb_modell_button = 'input_boolean.vvb_modell' # Button for turning on/off the model 
        self.vvb_info1 = 'input_text.vvb_information1' # For showing price informations in the HA UI
        self.vvb_info2 = 'input_text.vvb_information2'
        self.vvb_schedule = 'input_datetime.vvb_schedule' # For scheduling

        self.vvb_times = "/config/appdaemon/logs/saved_vvb_times.json" # Where the run times are saved
        self.vvb_scheduled_times = "/config/appdaemon/logs/scheduled_vvb_times.json" # For scheduling when to run vvb

        # When turning on/off the buttons, updates the info text in vvb window 
        self.get_entity(self.vvb_button1).listen_state(self.vvb_info) 
        self.get_entity(self.vvb_button2).listen_state(self.vvb_info)

        # Refresh the time right now
        self.constants()

        # Check if we should turn on/off vvb hourly
        self.run_hourly(self.vvb_on, datetime.time(hour=19, minute=0, second=0))
        self.run_hourly(self.vvb_off, datetime.time(hour=19, minute=0, second=0))

        # Every hour, run choose_run_time
        if self.get_state(self.VVB) == 'off':
            self.run_hourly(self.choose_run_time, datetime.time(hour=19, minute=0, second=0))

        # Check if we should turn on/off vvb hourly
        self.run_hourly(self.vvb_on, datetime.time(hour=19, minute=0, second=0))
        self.run_hourly(self.vvb_off, datetime.time(hour=19, minute=0, second=0))

        # Check if we should turn on/off vvb minutely for scheduling
        self.run_minutely(self.vvb_schedule_on, datetime.time(hour=19, minute=0, second=0))
        self.run_minutely(self.vvb_schedule_off, datetime.time(hour=19, minute=0, second=0))

        # Updates vvb info hourly
        self.run_hourly(self.vvb_info, datetime.time(hour=19, minute=0, second=0))

        # Check if Nord Pool API returned prices for the next day, if not we use a default time to run vvb
        self.run_daily(self.check_nordpool, datetime.time(hour=1, minute=5, second=0))

        # Turn on the first button and off the second button 
        if self.get_state(self.vvb_modell_button) == 'on':
            self.run_daily(self.button1_on, datetime.time(hour=17, minute=5, second=0))
            self.run_daily(self.button2_off, datetime.time(hour=17, minute=5, second=0))


        # Update the scheduling time when it's changed
        self.get_entity(self.vvb_schedule).listen_state(self.vvb_schedule_save)



    # Global variables
    def constants(self):
        self.hours_to_run = ceil(float(self.get_state(self.ENERGY_TO_FULL))/self.POWER)
        self.now = datetime.datetime.now()
        self.date = self.now.date()
        self.year = self.now.year
        self.month = self.now.month
        self.day = self.now.day
        self.hour = self.now.hour
        self.minute = self.now.minute


    # Returns a dicitonary of Nord Pool prices for today and maybe tomorrow (if published)
    def get_nordpool_price(self):
        nordPoolAPI = self.get_entity(self.NORDPOOL_ID).attributes
        bothRawDays = nordPoolAPI['raw_today'] + nordPoolAPI['raw_tomorrow']
        nordpool = {datetime.datetime.fromisoformat(hour['start']):hour['value'] for hour in bothRawDays}
        return nordpool


    # Given the spot prices, calculate the total price to run vvb for l hours at each hour
    def start_price(self, spot_prices, l):
        prices = list(spot_prices.values())
        hour_prices = list(spot_prices.items())
        run_prices = [(hour_prices[i][0],hour_prices[i+l-1][0] + datetime.timedelta(hours=1), sum(prices[i:i+l])) for i in range(len(prices)-l+1)]
        return run_prices


    # Chooses two cheapest time to run vvb
    def cheapest_start_time(self, spot_prices, l):

        self.constants()
        run_prices = [(x[0], x[1], x[2]) for x in self.start_price(self.get_nordpool_price(),l)]

        if len(self.get_nordpool_price()) > 24:
            night = sorted(run_prices[20:35-l], key = lambda x: x[2])
            afternoon = sorted(run_prices[34:43-l], key = lambda x: x[2])

        else: 
            night = sorted(run_prices[0:11-l], key=lambda x: x[2])
            afternoon = sorted(run_prices[10:19-l], key=lambda x: x[2])

        return sorted([night[0], afternoon[0]], key = lambda x: x[2])



    # Write a json file
    def writeToFile(self, file:str, data:dict):
        with open(file, 'w', encoding='utf-8') as logfile:
            #self.log(f"The dictionary has been written: {data}")
            logfile.write(json.dumps(data, indent=4, cls=DateTimeEncoder))



    # Read a json file 
    def readFromFile(self, file:str):
        with open(file, "r") as logfile:
            #self.log("File has been read!")
            return json.load(logfile)



    # Choose two times to run vvb based on prices given by Nord Pool API and saves them in a json file
    def choose_run_time(self, ignore = "ignore this"):

        self.constants()

        if self.hours_to_run < 2:
            self.hours_to_run = 2

        cheapest = self.cheapest_start_time(self.get_nordpool_price(), self.hours_to_run)
        c1, c2 = cheapest[0], cheapest[1]
        start_time1, end_time1, cost_to_run1 = c1[0], c1[1], c1[2]
        start_time2, end_time2, cost_to_run2 = c2[0], c2[1], c2[2]
        self.writeToFile(self.vvb_times, {
                                        "first": {"start" : start_time1,"end" : end_time1,"cost" : cost_to_run1}, 
                                        "second":{"start" : start_time2,"end" : end_time2,"cost" : cost_to_run2}
                                        })
        self.log('These times have been saved: ' + str({"first": {"start" : start_time1,"end" : end_time1,"cost" : cost_to_run1}, "second":{"start" : start_time2,"end" : end_time2,"cost" : cost_to_run2}}))
        self.vvb_info()



    # Checks if Nord Pool API has given the prices for tomorrow, if not we use a default time 
    def check_nordpool(self, ignore = "ignore this"):

        self.constants()
        
        check = list(self.get_nordpool_price().items())[-1][0].date()

        if check != self.date + datetime.timedelta(days=1):
            cheap_night_start_time = 2
            cheap_lunch_start_time = 13

            if self.hours_to_run < 2:
                self.hours_to_run = 2

            start_time1 = datetime.datetime(self.year, self.month, self.day+1, cheap_night_start_time)
            start_time2 = datetime.datetime(self.year, self.month, self.day+1, cheap_lunch_start_time)

            end_time1 = datetime.datetime(self.year, self.month, self.day+1, cheap_night_start_time + self.hours_to_run)
            end_time2 = datetime.datetime(self.year, self.month, self.day+1, cheap_lunch_start_time + self.hours_to_run)

            self.writeToFile(self.vvb_times, {
                                            "first": {"start" : start_time1,"end" : end_time1,"cost" : "VET EJ"}, 
                                            "second":{"start" : start_time2,"end" : end_time2,"cost" : "VET EJ"}
                                            })
                                            
            self.vvb_info()



    # For the text in vvb window
    def vvb_info(self, a="a", b="b", c="c", d="d", e="e"):

        self.constants()

        info = self.readFromFile(self.vvb_times)

        start1 = datetime.datetime.fromisoformat(info["first"]["start"])
        start2 = datetime.datetime.fromisoformat(info["first"]["end"])

        end1 = datetime.datetime.fromisoformat(info["second"]["start"])
        end2 = datetime.datetime.fromisoformat(info["second"]["end"])

        start_date1 = start1.date()
        start_date2 = end1.date()
        start_hour1 = start1.hour
        start_hour2 = end1.hour
        end_hour1 = start2.hour
        end_hour2 = end2.hour

        cost1 = info["first"]["cost"]
        cost2 = info["second"]["cost"]

        if self.date == start_date1:
            dag1 = 'Idag'
        elif self.date + datetime.timedelta(days=1) == start_date1:
            dag1 = 'Imorgon'
        elif self.date - datetime.timedelta(days=1) == start_date1:
            dag1 = 'Igår'
        else:
            dag1 = str(start_date1)

        if self.date == start_date2:
            dag2 = 'Idag'
        elif self.date + datetime.timedelta(days=1) == start_date2:
            dag2 = 'Imorgon'
        elif self.date - datetime.timedelta(days=1) == start_date2:
            dag2 = 'Igår'
        else: 
            dag2 = str(start_date2)

        if start_hour1 < 10: start_hour1 = '0' + str(start_hour1)
        if end_hour1 < 10: end_hour1 = '0' + str(end_hour1)
        if start_hour2 < 10: start_hour2 = '0' + str(start_hour2)
        if end_hour2 < 10: end_hour2 = '0' + str(end_hour2)
        

        if cost1 == "VET EJ" or cost2 == "VET EJ":
            self.set_state(self.vvb_button1, attributes={"friendly_name": f"{dag1} kl. {start_hour1} till {end_hour1} kostar {cost1} kr"})
            self.set_state(self.vvb_button2, attributes={"friendly_name": f"{dag2} kl. {start_hour2} till {end_hour2} kostar {cost2} kr"})
        else:
            self.set_state(self.vvb_button1, attributes={"friendly_name": f"{dag1} kl. {start_hour1} till {end_hour1} kostar {str(round(cost1,2)).replace('.',',')} kr"})
            self.set_state(self.vvb_button2, attributes={"friendly_name": f"{dag2} kl. {start_hour2} till {end_hour2} kostar {str(round(cost2,2)).replace('.',',')} kr"})

        self.log("VVB info has been updated")



    # For turning vvb on 
    def vvb_on(self, ignore = "ignore this"):

        self.constants()

        if self.get_state(self.vvb_modell_button) == 'on':
            run_time1 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["start"])
            run_time2 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["second"]["start"])

            run_time1_date = run_time1.date()
            run_time1_hour = run_time1.hour
            
            run_time2_date = run_time2.date()
            run_time2_hour = run_time2.hour

            if self.get_state(self.vvb_button1) == 'on' and self.date == run_time1_date and self.hour == run_time1_hour:
                self.turn_on(self.VVB)
                self.log("VVB has been turned on")

            if self.get_state(self.vvb_button2) == 'on' and self.date == run_time2_date and self.hour == run_time2_hour:
                self.turn_on(self.VVB)
                self.log("VVB has been turned on")



    # For turning vvb off 
    def vvb_off(self, ignore = "just ignore this"):

        self.constants()

        end_time1 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["first"]["end"])
        end_time2 = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_times)["second"]["end"])

        end_time1_date = end_time1.date()
        end_time1_hour = end_time1.hour
        
        end_time2_date = end_time2.date()
        end_time2_hour = end_time2.hour

        if self.get_state(self.VVB) == 'on': 
            if (self.date == end_time1_date and self.hour == end_time1_hour) or (self.date == end_time2_date and self.hour == end_time2_hour):
                self.turn_off(self.VVB)
                self.log("VVB has been turned off")



    # For scheduling
    def vvb_schedule_save(self, a="a", b="b", c="c", d="d", e="e"):
        self.writeToFile(self.vvb_scheduled_times, {"schedule_start": self.get_state(self.vvb_schedule), "schedule_end": "2023-01-01 00:00:00"})



    # For turning scheduled time on 
    def vvb_schedule_on(self, ignore = "just ignore this"):

        self.constants()

        start_time = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_scheduled_times)["schedule_start"])
        start_time_date = start_time.date()
        start_time_hour = start_time.hour
        start_time_minute = start_time.minute

        if self.date == start_time_date and self.hour == start_time_hour and self.minute == start_time_minute:
            end_time = start_time + datetime.timedelta(hours = self.hours_to_run) 
            self.writeToFile(self.vvb_scheduled_times, {"schedule_start": start_time, "schedule_end": end_time})
            self.turn_on(self.VVB)
            self.log("VVB has been turned on")



    # For turning scheduled time off
    def vvb_schedule_off(self, ignore = "just ignore this"):
        
        self.constants()

        end_time = datetime.datetime.fromisoformat(self.readFromFile(self.vvb_scheduled_times)["schedule_end"])
        end_time_date = end_time.date()
        end_time_hour = end_time.hour
        end_time_minute = end_time.minute

        if self.date == end_time_date and self.hour == end_time_hour and self.minute_now == end_time_minute:
            self.turn_off(self.VVB)
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























