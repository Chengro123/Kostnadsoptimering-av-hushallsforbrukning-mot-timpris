import hassapi as hass
import adbase as ad
import numpy as np
import datetime # Cannot use "as dt", since the eval-function then generates error when it reads "datetime.datetime".
import zoneinfo
import requests
import json

class lvpControl(hass.Hass, ad.ADBase):
    def initialize(self): # Sometimes initialize gets called with 6 (unnecessary) inputs
        # Read if the optimization should be active and run the code when the boolean changes
        activate_bool_id = 'input_boolean.toggle_lvp_optimizer'
        self.activeEntity = self.get_entity(activate_bool_id)
        self.activeEntity.listen_state(self.main)

        # Read which algorithm that should be used.
        algoritm_chooser_id = 'input_boolean.toggle_include_comftemp'
        self.incl_comf_temp = self.get_entity(algoritm_chooser_id)
        self.incl_comf_temp.listen_state(self.main)

        # Run the code when NordPool sensors attribute "tomorrow valid" is updated, since then it have received new prices
        self.nordpool_id="sensor.nordpool_kwh_se3_sek_3_10_025"
        self.nordpool = self.get_entity(self.nordpool_id)
        self.nordpool.listen_state(self.main, attribute = "tomorrow_valid")

        # Run the code if the sensor to display setpoints gets reset
        self.setpoint_id = "sensor.setpoints"
        self.setpoint = self.get_entity(self.setpoint_id)
        self.setpoint.listen_state(self.main)
        
        # Run if any comfort requirements changes
        self.mintemp_id = "input_number.mintemp"
        self.mintemp = self.get_entity(self.mintemp_id)
        self.mintemp.listen_state(self.main)

        self.maxtemp_id = "input_number.maxtemp"
        self.maxtemp = self.get_entity(self.maxtemp_id)
        self.maxtemp.listen_state(self.main)
        
        self.comforttemp_id = "input_number.comforttemp"
        self.comforttemp = self.get_entity(self.comforttemp_id)
        self.comforttemp.listen_state(self.main)

        self.coolingConst_id = 'input_number.cooling_constant'
        self.coolingConst = self.get_entity(self.coolingConst_id)
        self.coolingConst.listen_state(self.main)

        self.main() # Uncomment to run main

    def main(self,a="a",b="b",c="c",d="d",e="e"): # Sometimes main gets called with 6 (unnecessary) inputs
        self.settempfilename = "/config/appdaemon/logs/saved_setpoints.json"
        self.WEATHER_ID = "sensor.weather_data_via_api"

        # Defines comfort requirements, primarily from the sensors
        try:
            # Has to add str() after a state-listener is set on the id
            self.MINTEMP = int(float(self.get_entity(str(self.mintemp_id)).state))
        except:
            self.MINTEMP = 18
        try:
            self.MAXTEMP = int(float(self.get_entity(str(self.maxtemp_id)).state))
        except:
            self.MAXTEMP = 23
        try:
            self.COMFORTABLE = int(float(self.get_entity(str(self.comforttemp_id)).state))
        except:
            self.COMFORTABLE = 21
        # Air heat pump can only have integers as setpoints
        possibleTemps = np.flip(np.linspace(self.MINTEMP, self.MAXTEMP, self.MAXTEMP-self.MINTEMP+1, dtype = int)) 
        
        # The heat loss constant
        try:
            k = float(self.coolingConst.state)
        except:
            k = 0.04

        
        # Creates list of available Nordpool prices
        self.my_entity = self.get_entity(self.nordpool_id)
        actual_price = self.my_entity.attributes.today[:24]
        # If the data is unavailable, load latest known values 
        if len(actual_price)==0:
            with open(self.settempfilename, "r") as logfile:
                actual_price = json.load(logfile)["actual_price"]
        else:
            if self.my_entity.attributes.tomorrow_valid: actual_price += self.my_entity.attributes.tomorrow


        # If the "Reload all YAML-configuration"-button is pressed, the sensor for settemps is reset,
        # so the script should only reload it with its old values.
        data_exist = False
        # To prevent crashes if self.WEATHER_ID is not in the namespace, we use the latest available data for the calculations
        if self.WEATHER_ID in self.get_state():
            weatherAPI = self.get_entity(self.WEATHER_ID).attributes
            # To prevent crashes if the weather-api sensor exists but it has no "forecast"-key, e.g. after HA restart
            if "forecast" in weatherAPI:
                data_exist = True
                # Creates list of temperatures
                self.outsideTemp =  [hour["temp_c"]  for day in weatherAPI["forecast"]["forecastday"] for hour in day["hour"]]
                # We only want temps for hours with known prices, since those are the ones we can calculate setpoints for 
                self.outsideTemp = self.outsideTemp[:len(actual_price)]
        if not data_exist:
            with open(self.settempfilename, "r") as logfile:
                self.outsideTemp = json.load(logfile)["weather"]

        # Adjust actual_price with the COP of the air heat pump
        Temperature = np.array([-15, -10, -7, 2, 7, 12])
        COP = np.array([2.5, 2.8, 3.5, 5.2, 6.1, 7.4])    
        cop_at_temp = np.interp(self.outsideTemp, Temperature, COP)
        effective_price = actual_price/cop_at_temp

        # Calculate new settemperatures from the chosen algorithm
        try:
            incl_comf_temp_bool = self.incl_comf_temp.state == 'on'
        except:
            incl_comf_temp_bool = True
        if incl_comf_temp_bool:
            settemps = self.setTempMedKomfort(self.outsideTemp, effective_price, actual_price, possibleTemps, k)
        else:
            settemps = self.setTempUtanKomfort(self.outsideTemp, effective_price, k)
        # Sends the calculated settempes to the sensor to be plotted in the UI
        self.setSettempSensorAttr(settemps)

        # Creates dictionary of times and keys, but only includes "new" setpoints
        dtToday = datetime.datetime.now()
        settempstofile = {(datetime.datetime(dtToday.year,
                                            dtToday.month,
                                            dtToday.day,
                                            0,
                                            0
                                        )
                                +datetime.timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S")
                            : settemp
                        for hour, settemp in enumerate(settemps)
                        if hour>0 and not settemp == settemps[hour-1]
                        }

        # Saves the new settemps in a file, double quotes to work with json.loads()
        self.writeToFile(self.settempfilename,
                        {"settemps" : self.formatSettempsToSensor(settemps),
                        "runtimes"  : settempstofile,
                        "weather"   : self.outsideTemp,
                        "actual_price" : actual_price}
                        )

        # Fire the method since the settemps could have been changed.
        self.setNewSettemp(".")

        # Set a timer to look for a new settemp each hour
        self.adapi = self.get_ad_api()
        self.adapi.run_hourly(self.setNewSettemp, datetime.time(0, 1, 0))

    def setNewSettemp(self, ignore):
        dateToday = datetime.datetime.now()
        currentDatetime= str(datetime.datetime(dateToday.year,
                                        dateToday.month,
                                        dateToday.day,
                                        dateToday.hour,
                                        0))
        with open(self.settempfilename, "r") as logfile:
            settempDict = json.load(logfile)["runtimes"]
        response = self.get_lvp_state()
        # If there exist a new settemp in the file and the new temp is not the same as the current, change.
        # The latter condition should not be necessary, since the file only contains values for new settemps,
        # but make sure we do not do multiple set-commands if more than one listeners fire each hour.
        if currentDatetime in settempDict and int(response["setpoint"]) != settempDict[currentDatetime]:
            if self.activeEntity.state == 'on':
                self.log("Tidigare setTemp: " + response["setpoint"])
                self.set_lvp_state(setTemp=settempDict[currentDatetime])
                response = self.get_lvp_state()
                self.log(f'Nuvarande setTemp: {response["setpoint"]}, skulle bli {settempDict[currentDatetime]}')
            else:
                self.log(f"Temperaturen skulle bytt till {settempDict[currentDatetime]}, men optimeringen har avaktiverats, settemp = {self.COMFORTABLE}.")
                if not int(response["setpoint"]) == self.COMFORTABLE: self.set_lvp_state(self.COMFORTABLE)
        else: self.log(f'Ingen ny setpoint nu, {currentDatetime}.')
    def formatSettempsToSensor(self, settemps, starthour = 0):
        today = datetime.date.today()
        zone = zoneinfo.ZoneInfo("Europe/Stockholm")
        return[{"start": datetime.datetime(today.year, today.month, today.day, starthour, 0, tzinfo=zone)+datetime.timedelta(hours=i),
                "end"   : datetime.datetime(today.year, today.month, today.day, starthour+1, 0, tzinfo=zone)+datetime.timedelta(hours=i),
                "value" : sp} for i, sp in enumerate(settemps, starthour)]
    def setSettempSensorAttr(self, settemps, starthour = 0):
        formatedSettemps = self.formatSettempsToSensor(settemps, starthour)
        self.set_state(str(self.setpoint_id), state=".", attributes={"setpoints": formatedSettemps})
    def set_lvp_state(self, setTemp):
        url = "https://huskoll.se/API/openAPI.php/huskoll/set/"
        payload="token="+self.args["lvp_token"]+"&hwid="+self.args["lvp_hwid"]
        # A settemperature lower than 18 °C is not supported, so it then just get turned off.
        if setTemp < 18: payload+="&power=off"
        else: payload+="&power=on&mode=heat&fan=high&setpoint="+str(setTemp)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.request("POST", url, headers=headers, data=payload)
    def get_lvp_state(self):
        url = "https://huskoll.se/API/openAPI.php/huskoll/get/"
        payload="token="+self.args["lvp_token"]+"&hwid="+self.args["lvp_hwid"]
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)
    def writeToFile(self, file:str, data:dict):
        with open(file, 'w', encoding='utf-8') as logfile:
            logfile.write(json.dumps(data, indent=4, cls=DateTimeEncoder))

    def costFromSetpoints(self, settemps, price, outtemp=None):
        # Approximation of power in kWh for each possible setpoint, equals 100 W for 18 C and 600 W for 23 C.
        setpointPower = {temp:(temp*100-1700)/1000 for temp in settemps}
        return np.sum([setpointPower[t_set]*current_price for t_set, current_price in zip(settemps,price)])
        # If the outsude temps are unknown, the cost gets estimated purely from the approximated powers.
        if outtemp is None: return np.sum([setpointPower[t_set]*current_price for t_set, current_price in zip(settemps,price)])
        # Else open the database used to store P(t_set, dt)
        settempfilename = "/config/appdaemon/logs/db_settemps.json"
        with open(settempfilename, 'r') as settempfile:
            database = json.load(settempfile)
            sum = 0
            # Loop over each hour
            for i, (t_out,t_set,current_price) in enumerate(zip(outtemp, settemps, price)):
                # If there are previously logged powers for that settemp...
                if str(t_set) in database:
                    # ... approximate t_in-t_out for the current hour as 0.5(t_set^0+t_set^1)-t_out
                    dt = (t_set+settemps[min(len(settemps)-1,i+1)])/2-t_out
                    # save the list containing all logged dt for the current t_set
                    cur_dts = database[str(t_set)]['dt']
                    # calculate where in the array the dt should be (using a sorted list and binary search to obtain O(log n) time complexity).
                    i = self.bin(cur_dts, 0, len(cur_dts)-1, dt)
                    # If this dt already has a value, or if it is lower/higher than any logged values, use that/the closest value...
                    if cur_dts[i] == dt or i==0 or i==len(cur_dts)-1: pwr = cur_dts[i]
                    # ... else interpolate a new approximated power...
                    else: pwr = np.interp(dt, [i-1,i,i+1], database[str(t_set)]['power'][i-1:i+2])
                    # ... and lastly add this hours heating cost to the accumulated sum.
                    sum += current_price * pwr
                # ... otherwise calculate the cost the with the approximated values.
                else:
                    sum += setpointPower[t_set]*current_price
            return sum
    def printSetpointsAndCost(self, setpoints, price, name="unknown"):
        self.log(f'Totalt {round(self.costFromSetpoints(setpoints, price),2)} kr med algoritmen {name} för setpoints: \t')
        self.log(setpoints)
    def setTempMedKomfort(self, outtemp, effective_price, actual_price, possibleTemps, k):
        """First: Calculates how many hours it takes for the house to cool down from COMFORTABLE, COMFORTABLE+1, ..., MAXTEMP to MINTEMP.
        Second: Finds the best periods to place the different cooldown-hours for each staring temperature.
        Third: Choses which list of settemps gives the lowest cost and returns it.
        """
        def _hoursToCold(setpoint:int, out:list, MINTEMP:int, k:float=0.04) -> list:
            times = []
            for i in range(len(out)):
                j, T = i, setpoint
                while T > MINTEMP:
                    T = out[j]+(setpoint-out[j])*np.exp(-k*(j-i+1))
                    j += 1
                    if j >= len(out):
                        j = None
                        break
                if j is not None: times.append(j-i-1)
            return times
        def _highestConsecutive(effective_price:list, n:list, skip:list=[0]):
            """Returns starting hour for the n hours with the highest combined cost,
            excluding hours who includes a hour specified in the "skip"-list.
            Observe that the list should include element 0."""
            return np.argmax([np.sum(effective_price[i:i+n[i]])/n[i] if not any([hour in range(i,i+n[i]+1) for hour in skip]) else 0 for i in range(len(n))])
        def _multipleHighs(effective_price:list, n:list, nofExtremes:int):
            """Returns nofExtremes number of runhours, to avoid n hours long peaks, excluding hours specified in the skip-list."""
            runhours,skip = [],[0]        
            for i in range(nofExtremes):
                peakStart = _highestConsecutive(effective_price, n, skip)
                if not peakStart == 0:
                    runhours.append(peakStart-1) # -1 eftersom vi ska köra under timmen innan kullen
                    skip += list(range(peakStart-1,peakStart+1+n[peakStart])) # +2 pga timmar vi redan har planerat är timmen vi kör + n timmar då kullen är + timmen efter, då kan inte första kullen börja, eftersom vi måste lämna en timmes plats för att värma då
            return runhours
        def _fillTheBlank(runtimes:list, hoursToCold:list, MINTEMP:int, COMFORTABLE:int, hoursKnownPrice:int):
            return [hoursToCold["setpoint"] if hour in runtimes else MINTEMP if any([time<hour<time+hoursToCold["hours"][time]+1 for time in runtimes]) else COMFORTABLE for hour in range(hoursKnownPrice)]
        hoursToCold = [{"hours":_hoursToCold(temp, outtemp, self.MINTEMP, k), "setpoint": int(temp)} for temp in possibleTemps if temp >= self.COMFORTABLE]
        lowestCost, bestSetPoints = 1000, []
        for hours in hoursToCold:
            runtimes = _multipleHighs(effective_price, hours["hours"], round(len(effective_price)/(min(hours["hours"])+2)))
            setpoints = _fillTheBlank(runtimes, hours, self.MINTEMP, self.COMFORTABLE, len(effective_price))
            #self.printSetpointsAndCost(setpoints, actual_price, "setTempFromhourToCold_"+str(hours["setpoint"])) # Avkommentera för att skriva ut hur mycket varje variant kostar
            cost = self.costFromSetpoints(setpoints, actual_price, outtemp)
            if cost < lowestCost: lowestCost, bestSetPoints = cost, setpoints
        return bestSetPoints
    def setTempUtanKomfort(self, weather, current_price, k):
        def _hoursToCold(setpoint:int, out:list, MINTEMP:int, k:float) -> list:
            times = []
            for i in range(len(out)):
                j, T = i, setpoint
                while T > MINTEMP:
                    T = out[j]+(setpoint-out[j])*np.exp(-k*(j-i+1))
                    j += 1
                    if j >= len(out):
                        j = None
                        break
                if j is not None: times.append(j-i-1)
            return times

        tid_for_4_degrees =  _hoursToCold(self.MAXTEMP, weather, self.MINTEMP, k)
        # Om det är för varmt ute för att köra ska settemperaturerna vara mintemp hela dagen.
        if len(tid_for_4_degrees)==0: return [self.MINTEMP]*len(current_price)
        tid_for_4_degrees += [tid_for_4_degrees[-1]]*(len(weather)-len(tid_for_4_degrees))

        #Värden för dagens utomhustemperaturer
        tid_at_temp = tid_for_4_degrees# np.interp(weather, Temperature, tid_for_4_degrees)
        tid_at_temp = [round(x) for x in tid_at_temp]

        #derivative = np.gradient(current_price)
        medel_temp = round((self.MAXTEMP+self.MINTEMP)/2)

        # Initialize a variable to keep track of positive gradient streak
        temp_hours = [self.MINTEMP]*len(weather)
        i,k,control=0,0,0
        while i < len(weather)-1:
            if current_price[i] >= current_price[i+1]: #19 grader i nedförsbacke
                i += 1
            else:
                cooldown_time = tid_at_temp[i]
                j = i + cooldown_time
                k=i
                while k < j and k < len(weather)-1: #Kontroll om vi klarar hela toppen eller ej
                    if current_price[k] > current_price[k+1]:
                        control = 0
                        k = j
                    else:
                        control = 1
                        k += 1
                if control == 1 and k == len(weather)-1: #Om dagens slut har ökning
                    temp_hours[i] = medel_temp
                    i = len(weather)
                elif control == 1: #Vi behöver värma på väg upp mot toppen
                    m = j
                    while m < len(weather)-1:
                        if current_price[m] > current_price[m+1]:
                            cooldown_time2 = tid_at_temp[m]
                            if j > m-cooldown_time2:
                                temp_hours[i] = medel_temp
                                n = m-cooldown_time2
                                temp_hours[n] = self.MAXTEMP
                                i = m
                                m = len(weather)+1
                            else:
                                temp_hours[i] = self.MAXTEMP
                                i = j
                                m = len(weather)+1
                        elif m==len(weather)-2 and k==j:
                            temp_hours[i] = self.MAXTEMP
                            i=j
                            m=len(weather)+1
                        else:
                            m += 1
                elif control == 0: #Vi klarar hela toppen
                    temp_hours[i] = self.MAXTEMP
                    i = j
        return temp_hours
    def bin(self, arr:list, low:float, high:float, x:float) -> int:
        """Binary search, returns index of where the item should been if it not already is in the list."""
        if high >= low: 
            mid = (high + low) // 2
            if arr[mid] == x: return mid
            elif arr[mid] > x: return self.bin(arr, low, mid - 1, x)
            else: return self.bin(arr, mid + 1, high, x)
        else: return low # Element is not present in the array
class DateTimeEncoder(json.JSONEncoder):
        #Override the default method to be able to save settemps with datetime as keys
        def default(self, obj):
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
