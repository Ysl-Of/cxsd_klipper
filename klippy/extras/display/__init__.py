# Package definition for the extras/display directory
#
# Copyright (C) 2018  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from . import display

def load_config(config):
    return display.load_config(config)

def load_config_prefix(config):
    if not config.has_section('display'):
        raise config.error(
            """{"code":"key192", "msg": "A primary [display] section must be defined in printer.cfg to use auxilary displays", "values": []}""")
    name = config.get_name().split()[-1]
    if name == "display":
        raise config.error(
            """{"code":"key193", "msg": "Section name [display display] is not valid. Please choose a different postfix.", "values": []}""")
    return display.load_config(config)
