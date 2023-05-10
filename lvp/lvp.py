import yaml
from yaml.loader import SafeLoader
import requests
import hassapi as hass
import numpy as np
import datetime
from math import sqrt
import adbase as ad
class lvpCode(hass.Hass, ad.ADBase):
    def initialize(self):

        self.WEATHER_ID = 'sensor.weather_data_via_api'
        weatherAPI =  self.get_entity(self.WEATHER_ID).attributes
        weather = {}
        for day in weatherAPI['forecast']['forecastday']:
            for hour in day['hour']:
                weather[hour['time']] = {'temp':hour['temp_c'],
                                        'cloud': hour['cloud'],
                                        'wind': round(hour['wind_kph']/3.6,1),
                                        'humidity':hour['humidity']}
        #self.log(weather)
        
        self.NORDPOOL_ID = 'sensor.nordpool_kwh_se3_sek_3_10_025'

        #self.log(self.get_nordpool_price())
        P=self.get_nordpool_price()
        #self.log(self.setTempAfterPriceDeriv(P))

        #self.run_at(self.run(4), "14:34:00")
    

    def run(self, x):
        """Function to run at specific time"""
        self.log('Kördes!' + str(x))


    def get_nordpool_price(self):
        nordPoolAPI = self.get_entity(self.NORDPOOL_ID).attributes
        
        bothRawDays = nordPoolAPI['raw_today'] + nordPoolAPI['raw_tomorrow']
        nordpool = [hour['value'] for hour in bothRawDays]

        return nordpool

    def setTempAfterPriceDeriv(self,get_nordpool_price):

        temp_ut_idag=[]
        vind_idag=[]
        for hour in weather['hour']: 
            if hour.startswith(datetime.datetime.now().strftime('%Y-%m-%d')):
                temp_ut_idag.append(hour['temp'])
                vind_idag.append(hour['wind'])
        
        effektiv_temp = []
        for i in range(len(temp_ut_idag)):
            effektiv_temp.append(13.12 + 0.6215*temp_ut_idag[i]-13.956*vind_idag[i]**0.16 + 0.48669*temp_ut_idag[i]*vind_idag[i]**0.16)
        

        Temperature = np.array([-15, -10, -7, 2, 7, 12])
        COP = np.array([2.5, 2.8, 3.5, 5.2, 6.1, 7.4])
        Pdh = np.array([3.2, 3.2, 2.83, 1.7, 1.1, 1.18])
        tid_for_4_degrees = np.array([1, 1.5, 2, 3, 5, 8])

        interp_temps = np.linspace(-20, 25, 100)
        # Interpolate the COP and Pdh values at the new temperatures
        interp_cop = np.interp(interp_temps, Temperature, COP)
        interp_pdh = np.interp(interp_temps, Temperature, Pdh)
        interp_tid = np.interp(interp_temps, Temperature, tid_for_4_degrees)
        #energy_out = interp_pdh*interp_cop

        #Värden för dagens utomhustemperaturer
        pdh_at_temp = np.interp(temp_ut_idag, Temperature, Pdh)
        cop_at_temp = np.interp(temp_ut_idag, Temperature, COP)
        tid_at_temp = np.interp(outdoor_temp, Temperature, tid_for_4_degrees)
        tid_at_temp = [round(x) for x in tid_at_temp]
        current_price = pdh_at_temp*get_nordpool_price 

        hours = list(range(24))

        derivative = np.gradient(current_price)
        min_temp = 19
        max_temp = 23
        medel_temp = (max_temp+min_temp)/2

        # Initialize a variable to keep track of positive gradient streak
        temp_hours = [min_temp]*24
        i=0
        k=0
        control = 0

# Check if the derivative is positive or negative between each pair of consecutive hours

        while i < 23:
            if current_price[i] >= current_price[i+1]: #19 grader i nedförsbacke
                i += 1
            else:
                cooldown_time = tid_at_temp[i]
                j = i + cooldown_time
                k=i
                while k < j and k < 23: #Kontroll om vi klarar hela toppen eller ej
                    if current_price[k] > current_price[k+1]:
                        control = 0
                        k = j
                    else:
                        control = 1
                        k += 1
                if control == 1 and k == 23: #Om dagens slut har ökning
                    temp_hours[i] = medel_temp
                    i = 24
                elif control == 1: #Vi behöver värma på väg upp mot toppen
                    m = j
                    while m < 23:
                        if current_price[m] > current_price[m+1]:
                            cooldown_time2 = tid_at_temp[m]
                            if j > m-cooldown_time2:
                                temp_hours[i] = medel_temp
                                n = m-cooldown_time2
                                temp_hours[n] = max_temp
                                i = m
                                m = 25
                            else:
                                temp_hours[i] = max_temp
                                i = j
                                m = 25
                        else:
                            m += 1
                elif control == 0: #Vi klarar hela toppen
                    temp_hours[i] = max_temp
                    i = j
        return temp_hours
"""
    def ExpectedPrice(i,electricity_price,method):
        U=0.02 #Uppsaktad vid T_ut=6 och T_in=21.5
        temp_ut_idag=[]
        deltaT=[]
        for hour in response['forecast']['forecastday'][i]['hour']:
            temp_ut_idag.append(hour['temp_c'])
        temp_in=method(electricity_price, possibleTemps)
        for i,j in zip(temp_in, temp_ut_idag):
            deltaT.append(i-j)
        energy = [U * x for x in deltaT]
        Price = [j * k for j,k in zip(energy, electricity_price)]
        return sum(Price)


    #def DUMMY(i,electricity_price,T):
        U=0.02 #Uppsaktad vid T_ut=6 och T_in=21.5
        temp_ut_idag=[]
        temp_in=[]
        deltaT=[]
        for hour in response['forecast']['forecastday'][i]['hour']:
            temp_ut_idag.append(hour['temp_c'])
            temp_in.append(T)
        #deltaT=temp_in-temp_ut_idag
        for i,j in zip(temp_in, temp_ut_idag):
            deltaT.append(i-j)
        energy = [U * x for x in deltaT]
        Price = [j * k for j,k in zip(energy, electricity_price)]
        return sum(Price)

    print(DUMMY(0,electricity_price,21))
    """