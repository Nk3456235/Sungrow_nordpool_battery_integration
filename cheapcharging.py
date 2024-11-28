import appdaemon.plugins.hass.hassapi as hass
import datetime

class CheapChargingApp(hass.Hass):

    def initialize(self):
        # Set up a listener to update every time the Nordpool sensor updates
        self.listen_state(self.update_cheap_hours, "sensor.nordpool_kwh_se3_sek_3_10_025")
        
        # Create the sensor initially
        self.create_cheap_hours_sensor()

    def update_cheap_hours(self, entity, attribute, old_state, new_state):
        """This function calculates the two cheapest hours for charging from 10:00 to 16:00, compares prices, and decides whether to start charging."""
        # Fetch today's prices from the Nordpool sensor
        today_prices = self.get_state("sensor.nordpool_kwh_se3_sek_3_10_025", attribute="today")
        
        # Get prices for 10:00 to 16:00 (indexes 10 to 16)
        hours_10_to_16 = today_prices[10:17]
        
        # Sort by price and pick the two cheapest hours
        sorted_hours = sorted(hours_10_to_16, key=lambda x: x['price'])
        cheapest_hours = sorted_hours[:2]
        
        # If less than two hours are found, we skip the charging setup
        if len(cheapest_hours) < 2:
            self.set_state("sensor.cheap_chosen_hours_day_charging", state="No cheap hours found")
            return
        
        # Calculate the mean price for the two cheapest hours (10:00-16:00)
        cheap_mean = (cheapest_hours[0]['price'] + cheapest_hours[1]['price']) / 2
        
        # Get the prices for hours 16:00 to 21:00 (indexes 16 to 21)
        hours_16_to_21 = today_prices[16:22]
        
        # Calculate the mean price for hours 16:00 to 21:00
        later_mean = sum([hour['price'] for hour in hours_16_to_21]) / len(hours_16_to_21)
        
        # Now compare the two mean prices (the difference must be greater than 60 for charging to proceed)
        if (later_mean - cheap_mean) > 60:
            # Check battery level (below 65% for charging to start)
            battery_level = float(self.get_state("sensor.battery_level"))
            if battery_level < 65:
                self.start_charging(cheapest_hours)
            else:
                self.set_state("sensor.cheap_chosen_hours_day_charging", state="Battery level too high")
        else:
            self.set_state("sensor.cheap_chosen_hours_day_charging", state="Price difference too small")

    def start_charging(self, cheapest_hours):
        """Starts charging for the two cheapest hours."""
        # Get the start times for the two cheapest hours and format them
        hour_1_start = self.format_time(cheapest_hours[0]['start'])
        hour_2_start = self.format_time(cheapest_hours[1]['start'])

        # Update the sensor with the two chosen charging hours
        sensor_value = f"{hour_1_start} to {hour_2_start}"
        self.set_state("sensor.cheap_chosen_hours_day_charging", state=sensor_value)
        
        # Start the charging process using the input_select actions
        self.log(f"Starting charging for the hours {sensor_value}")
        
        # Set the EMS mode to Forced mode
        self.call_service("input_select/select_option", 
                          entity_id="input_select.set_sg_ems_mode", 
                          option="Forced mode")

        # Set the battery charging command to Forced charge
        self.call_service("input_select/select_option", 
                          entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd", 
                          option="Forced charge")

        # Schedule the stop for each of the two hours (even if non-sequential)
        self.run_in(self.stop_charging, self.calculate_seconds_until_end(cheapest_hours[0]['end'], 0))
        self.run_in(self.stop_charging, self.calculate_seconds_until_end(cheapest_hours[1]['end'], 1))

    def stop_charging(self, kwargs):
        """Stops charging after the hour ends."""
        hour_index = kwargs["data"]
        self.log(f"Stopping charging for hour {hour_index + 1}")
        
        # Stop charging by setting the modes back to "Stop" and "Forced mode"
        self.call_service("input_select/select_option", 
                          entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd", 
                          option="Stop (default)")  # Set to stop charge

        self.call_service("input_select/select_option", 
                          entity_id="input_select.set_sg_ems_mode", 
                          option="Forced mode")  # Ensure mode is forced
        
        # Optional: Add a small delay to allow the system to process the change
        self.call_service("script.turn_on", entity_id="script.delay_2_seconds")

    def calculate_seconds_until_end(self, end_time, hour_index):
        """Calculates the seconds until the hour ends."""
        now = datetime.datetime.now()
        end_time = datetime.datetime.fromtimestamp(end_time)
        delta = end_time - now
        return delta.total_seconds()

    def format_time(self, timestamp):
        """Helper function to format the timestamp to local time."""
        local_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return local_time

    def create_cheap_hours_sensor(self):
        """Creates the cheap chosen hours sensor."""
        self.set_state("sensor.cheap_chosen_hours_day_charging", state="No cheap hours selected yet")



cheap_charging_app:
  module: cheap_charging_app
  class: CheapChargingApp
