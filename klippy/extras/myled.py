# Support for MyLed
#
# Copyright (C) 2022  fengxs <1289244886@qq.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging

PIN_MIN_TIME = 0.300


class MyLed:
    def __init__(self, config):
        self.toggle = False
        self.is_active = True
        self.last_print_time = 0.
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        ppins = self.printer.lookup_object('pins')
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        self.mcu_led = ppins.setup_pin('digital_out', config.get('pin'))
        # # my led updating
        self.myled_update_timer = self.reactor.register_timer(
            self.led_update_event)
        self.mcu_led.setup_start_value(0, 0)


    def handle_ready(self):
        # Start led update timer
        self.reactor.update_timer(self.myled_update_timer,
                                  self.reactor.NOW)

    def led_update_event(self, eventtime):
        print_time = self.mcu_led.get_mcu().estimated_print_time(eventtime)
        print_time = max(print_time, self.last_print_time + PIN_MIN_TIME)
        logging.info("<<<<<<<<<<<<<<<<<<<<<<led test>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>%s"%print_time)
        if self.toggle:
            logging.info("......................led ON...........................")
            self.set_led_on(print_time)
            self.toggle = False
        else:
            logging.info("//////////////////////led OFF>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            self.set_led_off(print_time)
            self.toggle = True
        self.last_print_time = print_time
        if self.is_active:
            return eventtime + 1
        else:
            return self.reactor.NEVER

    def set_led_on(self, print_time):
        self.mcu_led.set_digital(print_time + PIN_MIN_TIME, 1)

    def set_led_off(self, print_time):
        self.mcu_led.set_digital(print_time + PIN_MIN_TIME, 0)

def load_config(config):
    return MyLed(config)
