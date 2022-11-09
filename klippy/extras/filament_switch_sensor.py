# Generic Filament Sensor Module
#
# Copyright (C) 2019  Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging

class RunoutHelper:
    def __init__(self, config):
        self.name = config.get_name().split()[-1]
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        ppins = self.printer.lookup_object('pins')
        self.gas = ppins.setup_pin('digital_out', config.get('gas_pin'))
        self.gas.setup_start_value(0, 0)
        self.gcode = self.printer.lookup_object('gcode')
        # Read config
        self.runout_pause = config.getboolean('pause_on_runout', True)
        if self.runout_pause:
            self.printer.load_object(config, 'pause_resume')
        self.runout_gcode = self.insert_gcode = None
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        if self.runout_pause or config.get('runout_gcode', None) is not None:
            self.runout_gcode = gcode_macro.load_template(
                config, 'runout_gcode', '')
        if config.get('insert_gcode', None) is not None:
            self.insert_gcode = gcode_macro.load_template(
                config, 'insert_gcode')
        self.pause_delay = config.getfloat('pause_delay', .5, above=.0)
        self.event_delay = config.getfloat('event_delay', 3., above=0.)
        # Internal state
        self.min_event_systime = self.reactor.NEVER
        self.filament_present = False
        self.sensor_enabled = True
        self.add_filament_time = 0
        self.add_filament_cnt = 0
        self.add_filament_status = False
        self.manual_add_filament_status = False
        self.manual_add_filament_time = 0
        # Register commands and event handlers
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.filament_update_timer = self.reactor.register_timer(
            self.filament_update_event)
        self.gcode.register_mux_command(
            "QUERY_FILAMENT_SENSOR", "SENSOR", self.name,
            self.cmd_QUERY_FILAMENT_SENSOR,
            desc=self.cmd_QUERY_FILAMENT_SENSOR_help)
        self.gcode.register_mux_command(
            "SET_FILAMENT_SENSOR", "SENSOR", self.name,
            self.cmd_SET_FILAMENT_SENSOR,
            desc=self.cmd_SET_FILAMENT_SENSOR_help)
        self.gcode.register_mux_command(
            "MANUAL_ADD_FIALMENT", "SENSOR", self.name,
            self.cmd_MANUAL_ADD_FIALMENT,
            desc=self.cmd_MANUAL_ADD_FIALMENT_help)
    def _handle_ready(self):
        self.min_event_systime = self.reactor.monotonic() + 2.
        self.reactor.update_timer(self.filament_update_timer,
                                  self.reactor.NOW)
    def _runout_event_handler(self, eventtime):
        # Pausing from inside an event requires that the pause portion
        # of pause_resume execute immediately.
        pause_prefix = ""
        if self.runout_pause:
            pause_resume = self.printer.lookup_object('pause_resume')
            pause_resume.send_pause_command()
            pause_prefix = "PAUSE\n"
            self.printer.get_reactor().pause(eventtime + self.pause_delay)
        self._exec_gcode(pause_prefix, self.runout_gcode)
    def _insert_event_handler(self, eventtime):
        self._exec_gcode("", self.insert_gcode)
    def _exec_gcode(self, prefix, template):
        try:
            self.gcode.run_script(prefix + template.render() + "\nM400")
        except Exception:
            logging.exception("Script running error")
        self.min_event_systime = self.reactor.monotonic() + self.event_delay
    def note_filament_present(self, is_filament_present):
        if is_filament_present == self.filament_present:
            return
        self.filament_present = is_filament_present
        eventtime = self.reactor.monotonic()
        if eventtime < self.min_event_systime or not self.sensor_enabled:
            # do not process during the initialization time, duplicates,
            # during the event delay time, while an event is running, or
            # when the sensor is disabled
            return
        # Determine "printing" status
        idle_timeout = self.printer.lookup_object("idle_timeout")
        is_printing = idle_timeout.get_status(eventtime)["state"] == "Printing"
        # Perform filament action associated with status change (if any)
        if is_filament_present:
            if not is_printing and self.insert_gcode is not None:
                # insert detected
                self.min_event_systime = self.reactor.NEVER
                logging.info(
                    "Filament Sensor %s: insert event detected, Time %.2f" %
                    (self.name, eventtime))
                self.reactor.register_callback(self._insert_event_handler)
        elif is_printing and self.runout_gcode is not None:
            # runout detected
            self.min_event_systime = self.reactor.NEVER
            logging.info(
                "Filament Sensor %s: runout event detected, Time %.2f" %
                (self.name, eventtime))
            self.reactor.register_callback(self._runout_event_handler)
    def get_status(self, eventtime):
        return {
            "filament_detected": bool(self.filament_present),
            "enabled": bool(self.sensor_enabled)}
    cmd_QUERY_FILAMENT_SENSOR_help = "Query the status of the Filament Sensor"
    def cmd_QUERY_FILAMENT_SENSOR(self, gcmd):
        if self.filament_present:
            msg = "Filament Sensor %s: filament detected" % (self.name)
        else:
            msg = "Filament Sensor %s: filament not detected" % (self.name)
        gcmd.respond_info(msg)
    cmd_SET_FILAMENT_SENSOR_help = "Sets the filament sensor on/off"
    def cmd_SET_FILAMENT_SENSOR(self, gcmd):
        self.sensor_enabled = gcmd.get_int("ENABLE", 1)
    cmd_MANUAL_ADD_FIALMENT_help = "Set manual add filament"
    def cmd_MANUAL_ADD_FIALMENT(self, gcmd=None):
        self.manual_add_filament_status = True

    def filament_update_event(self, eventtime):
        # Determine "printing" status
        idle_timeout = self.printer.lookup_object("idle_timeout")
        is_printing = idle_timeout.get_status(eventtime)["state"]
        logging.info("printing status:%s" % is_printing)
        systime = self.reactor.monotonic()
        print_time = self.gas.get_mcu().estimated_print_time(systime)

        if self.manual_add_filament_status:
            self.gas.set_digital(print_time + 0.5, 1)
            self.manual_add_filament_time += 1
            if self.manual_add_filament_time >= 15:
                self.manual_add_filament_time = 0
                self.manual_add_filament_status = False
            return eventtime + 1

        if self.add_filament_status:
            self.gas.set_digital(print_time + 0.5, 1)
            self.add_filament_time += 1
            if self.add_filament_time >= 15:
                self.add_filament_time = 0
                self.add_filament_cnt += 1
                self.add_filament_status = False
            return eventtime + 1

        if self.filament_present:
            self.add_filament_cnt = 0

        if not self.filament_present and self.add_filament_cnt < 3 and is_printing == "Printing":
            self.add_filament_status = True
            self.gas.set_digital(print_time + 0.5, 0)
            return eventtime + 1

        if self.add_filament_cnt >= 3:
            self.add_filament_time = 0
            self.add_filament_cnt = 0
            self.add_filament_status = False
            self.gas.set_digital(print_time + 0.5, 0)
            self.gcode.run_script("PAUSE" + "\nM400")
            logging.info("pause printing.")
            return eventtime + 1

        self.gas.set_digital(print_time + 0.5, 0)
        return eventtime + 1


class SwitchSensor:
    def __init__(self, config):
        printer = config.get_printer()
        buttons = printer.load_object(config, 'buttons')
        switch_pin = config.get('switch_pin')
        buttons.register_buttons([switch_pin], self._button_handler)
        self.runout_helper = RunoutHelper(config)
        self.get_status = self.runout_helper.get_status
    def _button_handler(self, eventtime, state):
        self.runout_helper.note_filament_present(state)

def load_config_prefix(config):
    return SwitchSensor(config)
