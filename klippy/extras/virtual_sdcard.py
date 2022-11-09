# Virtual sdcard support (print files directly from a host g-code file)
#
# Copyright (C) 2018  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import imp
import os, logging

VALID_GCODE_EXTS = ['gcode', 'g', 'gco']
LAYER_KEYS = [";LAYER", "; layer", "; LAYER", ";AFTER_LAYER_CHANGE"]

class VirtualSD:
    def __init__(self, config):
        printer = config.get_printer()
        printer.register_event_handler("klippy:shutdown", self.handle_shutdown)
        self.printer = printer
        # sdcard state
        sd = config.get('path')
        self.sdcard_dirname = os.path.normpath(os.path.expanduser(sd))
        self.current_file = None
        self.file_position = self.file_size = 0
        # Print Stat Tracking
        self.print_stats = printer.load_object(config, 'print_stats')
        # Work timer
        self.reactor = printer.get_reactor()
        self.must_pause_work = self.cmd_from_sd = False
        self.next_file_position = 0
        self.work_timer = None
        if printer.start_args.get("apiserver")[-1] != "s":
            self.index = printer.start_args.get("apiserver")[-1]
        else:
            self.index = "1"
        # Register commands
        self.gcode = printer.lookup_object('gcode')
        for cmd in ['M20', 'M21', 'M23', 'M24', 'M25', 'M26', 'M27']:
            self.gcode.register_command(cmd, getattr(self, 'cmd_' + cmd))
        for cmd in ['M28', 'M29', 'M30']:
            self.gcode.register_command(cmd, self.cmd_error)
        self.gcode.register_command(
            "SDCARD_RESET_FILE", self.cmd_SDCARD_RESET_FILE,
            desc=self.cmd_SDCARD_RESET_FILE_help)
        self.gcode.register_command(
            "SDCARD_PRINT_FILE", self.cmd_SDCARD_PRINT_FILE,
            desc=self.cmd_SDCARD_PRINT_FILE_help)
        # self.printer = printer
        self.count = 0
    def handle_shutdown(self):
        if self.work_timer is not None:
            self.must_pause_work = True
            try:
                readpos = max(self.file_position - 1024, 0)
                readcount = self.file_position - readpos
                self.current_file.seek(readpos)
                data = self.current_file.read(readcount + 128)
            except:
                logging.exception("virtual_sdcard shutdown read")
                return
            logging.info("Virtual sdcard (%d): %s\nUpcoming (%d): %s",
                         readpos, repr(data[:readcount]),
                         self.file_position, repr(data[readcount:]))
    def stats(self, eventtime):
        if self.work_timer is None:
            return False, ""
        return True, "sd_pos=%d" % (self.file_position,)
    def get_file_list(self, check_subdirs=False):
        if check_subdirs:
            flist = []
            for root, dirs, files in os.walk(
                    self.sdcard_dirname, followlinks=True):
                for name in files:
                    ext = name[name.rfind('.')+1:]
                    if ext not in VALID_GCODE_EXTS:
                        continue
                    full_path = os.path.join(root, name)
                    r_path = full_path[len(self.sdcard_dirname) + 1:]
                    size = os.path.getsize(full_path)
                    flist.append((r_path, size))
            return sorted(flist, key=lambda f: f[0].lower())
        else:
            dname = self.sdcard_dirname
            try:
                filenames = os.listdir(self.sdcard_dirname)
                return [(fname, os.path.getsize(os.path.join(dname, fname)))
                        for fname in sorted(filenames, key=str.lower)
                        if not fname.startswith('.')
                        and os.path.isfile((os.path.join(dname, fname)))]
            except:
                logging.exception("virtual_sdcard get_file_list")
                raise self.gcode.error("Unable to get file list")
    def get_status(self, eventtime):
        return {
            'file_path': self.file_path(),
            'progress': self.progress(),
            'is_active': self.is_active(),
            'file_position': self.file_position,
            'file_size': self.file_size,
        }
    def file_path(self):
        if self.current_file:
            return self.current_file.name
        return None
    def progress(self):
        if self.file_size:
            # logging.info("progress:%f, file_position:%s, file_size:%f" % (
            # float(self.file_position) / self.file_size, self.file_position, self.file_size))
            try:
                return float(self.file_position) / self.file_size
            except Exception as e:
                logging.exception(e)
                return 0.
        else:
            return 0.
    def is_active(self):
        return self.work_timer is not None
    def do_pause(self):
        if self.work_timer is not None:
            self.must_pause_work = True
            while self.work_timer is not None and not self.cmd_from_sd:
                self.reactor.pause(self.reactor.monotonic() + .001)
    def do_resume(self):
        if self.work_timer is not None:
            logging.error("do_resume work_timer is not None")
            raise self.gcode.error("""{"code":"key217", "msg": "SD busy" "values": []}""")
        self.must_pause_work = False
        self.work_timer = self.reactor.register_timer(
            self.work_handler, self.reactor.NOW)
    def do_cancel(self):
        if self.current_file is not None:
            self.do_pause()
            self.current_file.close()
            self.current_file = None
            self.print_stats.note_cancel()
        self.file_position = self.file_size = 0.
    # G-Code commands
    def cmd_error(self, gcmd):
        raise gcmd.error("SD write not supported")
    def _reset_file(self):
        if self.current_file is not None:
            self.do_pause()
            self.current_file.close()
            self.current_file = None
        self.file_position = self.file_size = 0.
        self.print_stats.reset()
    cmd_SDCARD_RESET_FILE_help = "Clears a loaded SD File. Stops the print "\
        "if necessary"
    def cmd_SDCARD_RESET_FILE(self, gcmd):
        if self.cmd_from_sd:
            raise gcmd.error(
                """{"code":"key131", "msg": "SDCARD_RESET_FILE cannot be run from the sdcard", "values": []}""")
        self._reset_file()
    cmd_SDCARD_PRINT_FILE_help = "Loads a SD file and starts the print.  May "\
        "include files in subdirectories."
    def cmd_SDCARD_PRINT_FILE(self, gcmd):
        if self.work_timer is not None:
            logging.error("cmd_SDCARD_PRINT_FILE work_timer is not None")
            raise gcmd.error("""{"code":"key217", "msg": "SD busy" "values": []}""")
        self._reset_file()
        filename = gcmd.get("FILENAME")
        if filename[0] == '/':
            filename = filename[1:]
        self._load_file(gcmd, filename, check_subdirs=True)
        self.do_resume()
    def cmd_M20(self, gcmd):
        # List SD card
        files = self.get_file_list()
        gcmd.respond_raw("Begin file list")
        for fname, fsize in files:
            gcmd.respond_raw("%s %d" % (fname, fsize))
        gcmd.respond_raw("End file list")
    def cmd_M21(self, gcmd):
        # Initialize SD card
        gcmd.respond_raw("SD card ok")
    def cmd_M23(self, gcmd):
        # Select SD file
        if self.work_timer is not None:
            logging.error("cmd_M23 work_timer is not None")
            raise gcmd.error("""{"code":"key217", "msg": "SD busy" "values": []}""")
        self._reset_file()
        try:
            orig = gcmd.get_commandline()
            filename = orig[orig.find("M23") + 4:].split()[0].strip()
            if '*' in filename:
                filename = filename[:filename.find('*')].strip()
        except:
            raise gcmd.error("""{"code":"key120", "msg": "Unable to extract filename", "values": []}""")
        if filename.startswith('/'):
            filename = filename[1:]
        self._load_file(gcmd, filename)
    def _load_file(self, gcmd, filename, check_subdirs=False):
        files = self.get_file_list(check_subdirs)
        flist = [f[0] for f in files]
        files_by_lower = { fname.lower(): fname for fname, fsize in files }
        fname = filename
        try:
            if fname not in flist:
                fname = files_by_lower[fname.lower()]
            fname = os.path.join(self.sdcard_dirname, fname)
            f = open(fname, 'r')
            f.seek(0, os.SEEK_END)
            fsize = f.tell()
            f.seek(0)
        except Exception as e:
            # logging.exception("virtual_sdcard file open")
            logging.exception(e)
            raise gcmd.error("""{"code":"key121", "msg": "Unable to open file", "values": []}""")
        gcmd.respond_raw("File opened:%s Size:%d" % (filename, fsize))
        gcmd.respond_raw("File selected")
        self.current_file = f
        self.file_position = 0
        self.file_size = fsize
        self.print_stats.set_current_file(filename)
    def cmd_M24(self, gcmd):
        # Start/resume SD print
        self.do_resume()
    def cmd_M25(self, gcmd):
        # Pause SD print
        self.do_pause()
    def cmd_M26(self, gcmd):
        # Set SD position
        if self.work_timer is not None:
            logging.error("cmd_M26 work_timer is not None")
            raise gcmd.error("SD busy")
        pos = gcmd.get_int('S', minval=0)
        self.file_position = pos
    def cmd_M27(self, gcmd):
        # Report SD print status
        if self.current_file is None:
            gcmd.respond_raw("Not SD printing.")
            return
        gcmd.respond_raw("SD printing byte %d/%d"
                         % (self.file_position, self.file_size))
    def get_file_position(self):
        return self.next_file_position
    def set_file_position(self, pos):
        self.next_file_position = pos
    def is_cmd_from_sd(self):
        return self.cmd_from_sd
    
    def record_status(self, path, file_name):
        gcode_move = self.printer.lookup_object('gcode_move')
        gcode_move.cmd_CX_SAVE_GCODE_STATE(self.file_position, path, file_name)
    
    # Background work timer
    def work_handler(self, eventtime):
        import time
        # When the nozzle is moved
        output_pre_video_path = "/mnt/UDISK/.crealityprint/video"
        try:
            import yaml
            with open("/mnt/UDISK/.crealityprint/time_lapse.yaml") as f:
                config_data = yaml.load(f.read(), Loader=yaml.Loader)
            # if timelapse_position == 1 then When the nozzle is moved
            timelapse_postion = int(config_data.get('1').get("position", 0))
            enable_delay_photography = config_data.get('1').get("enable_delay_photography", False)
            frequency = int(config_data.get("1").get("frequency", 1))

            brain_fps = config_data.get("1").get("fps", "MP4-15")
            if brain_fps == "MP4-15":
                output_framerate = 15
            else:
                output_framerate = 25
            filename = os.path.basename(self.file_path())
        except Exception as e:
            logging.exception(e)
            timelapse_postion = 0
            frequency = 1
            enable_delay_photography = False

        base_shoot_path = "/mnt/UDISK/delayed_imaging/test.264"
        test_jpg_path = output_pre_video_path + "/test.jpg"
        try:
            if enable_delay_photography:
                rm_video = "rm -f " + base_shoot_path
                logging.info(rm_video)
                os.system(rm_video)
        except:
            pass

        layer_count = 0
        video0_status = True
        logging.info("get enable_delay_photography:%s timelapse position is %s" % (enable_delay_photography, timelapse_postion))
        logging.info("Starting SD card print (position %d)", self.file_position)

        import threading
        t = threading.Thread(target=self._upload_remote_log_start_print)
        t.start()

        mcu = self.printer.lookup_object('mcu', None)
        pre_serial = mcu._serial.serial_dev.port.split("/")[-1]

        import os, json
        path = "/mnt/UDISK/%s_gcode_coordinate.save" % pre_serial
        path2 = "/mnt/UDISK/.crealityprint/print_switch.txt"
        print_switch = False
        if os.path.exists(path2):
            try:
                with open(path2, "r") as f:
                    ret = json.loads(f.read())
                    print_switch = ret.get("switch", False)
            except Exception as err:
                pass
        state = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    state = json.loads(f.read())
                    self.file_position = int(state.get("file_position", 0))
                    gcode = self.printer.lookup_object('gcode')
                    gcode.run_script("M140 S60")
                    gcode.run_script("M109 S200")

                    gcode_move = self.printer.lookup_object('gcode_move', None)
                    gcode_move.cmd_CX_RESTORE_GCODE_STATE(path)
            except Exception as err:
                pass
        
        self.reactor.unregister_timer(self.work_timer)
        try:
            self.current_file.seek(self.file_position)
        except:
            logging.exception("virtual_sdcard seek")
            self.work_timer = None
            return self.reactor.NEVER
        self.print_stats.note_start()
        gcode_mutex = self.gcode.get_mutex()
        partial_input = ""
        lines = []
        error_message = None
        while not self.must_pause_work:
            if not lines:
                # Read more data
                try:
                    data = self.current_file.read(8192)
                except:
                    logging.exception("virtual_sdcard read")
                    break
                if not data:
                    # End of file
                    self.current_file.close()
                    self.current_file = None
                    logging.info("Finished SD card print")
                    self.gcode.respond_raw("Done printing file")
                    break
                lines = data.split('\n')
                lines[0] = partial_input + lines[0]
                partial_input = lines.pop()
                lines.reverse()
                self.reactor.pause(self.reactor.NOW)
                continue
            # Pause if any other request is pending in the gcode class
            if gcode_mutex.test():
                self.reactor.pause(self.reactor.monotonic() + 0.100)
                continue
            # Dispatch command
            self.cmd_from_sd = True
            line = lines.pop()
            next_file_position = self.file_position + len(line) + 1
            self.next_file_position = next_file_position
            try:
                if print_switch and self.count % 50 == 0:
                    self.record_status(path, self.current_file.name)
                # logging.info(line)
                if enable_delay_photography == True and video0_status == True:
                    for layer_key in LAYER_KEYS:
                        if ";LAYER_COUNT:" in layer_key:
                            break
                        if line.startswith(layer_key):
                            if layer_count % int(frequency) == 0:
                                if not os.path.exists("/dev/video0"):
                                    video0_status = False
                                    continue
                                # line = "TIMELAPSE_TAKE_FRAME"
                                logging.info("timelapse_postion: %d" % timelapse_postion)
                                # logging.info(line)
                                if timelapse_postion:
                                    toolhead = self.printer.lookup_object('toolhead')
                                    X, Y, Z, E = toolhead.get_position()
                                    # 1. Pull back and lift first
                                    cmd_list1 = ["M83", "G1 E-4", "M82"]
                                    for sub_cmd in cmd_list1:
                                        logging.info(sub_cmd)
                                        self.gcode.run_script(sub_cmd)
                                    time.sleep(0.8)
                                    cmd_list2 = ["G91", "G1 Z2", "G90"]
                                    for sub_cmd in cmd_list2:
                                        logging.info(sub_cmd)
                                        self.gcode.run_script(sub_cmd)
                                    time.sleep(0.4)

                                    # 2. move to the specified position
                                    cmd = "G0 X5 Y150 F9000"
                                    logging.info(cmd)
                                    self.gcode.run_script(cmd)
                                    cmd_wait_for_stepper = "M400"
                                    logging.info(cmd_wait_for_stepper)
                                    self.gcode.run_script(cmd_wait_for_stepper)

                                    try:
                                        capture_shell = "capture &"
                                        logging.info(capture_shell)
                                        os.system(capture_shell)
                                        if not os.path.exists(test_jpg_path):
                                            snapshot_cmd = "wget http://localhost:8080/?action=snapshot -O %s" % test_jpg_path
                                            logging.info(snapshot_cmd)
                                            os.system(snapshot_cmd)
                                    except:
                                        pass

                                    # 3. move back
                                    cmd_list3 = ["M83", "G1 E3", "M82"]
                                    for sub_cmd in cmd_list3:
                                        logging.info(sub_cmd)
                                        self.gcode.run_script(sub_cmd)
                                    time.sleep(0.4)
                                    move_back_cmd = "G1 X%s Y%s Z%s F10000" % (X, Y, Z)
                                    logging.info(move_back_cmd)
                                    self.gcode.run_script(move_back_cmd)
                                    cmd_list4 = ["G91", "G1 Z-2", "G90"]
                                    for sub_cmd in cmd_list4:
                                        logging.info(sub_cmd)
                                        self.gcode.run_script(sub_cmd)
                                else:
                                    try:
                                        capture_shell = "capture &"
                                        logging.info(capture_shell)
                                        os.system(capture_shell)
                                        if not os.path.exists(test_jpg_path):
                                            snapshot_cmd = "wget http://localhost:8080/?action=snapshot -O %s" % test_jpg_path
                                            logging.info(snapshot_cmd)
                                            os.system(snapshot_cmd)
                                    except:
                                        pass
                            layer_count += 1
                            break
                self.gcode.run_script(line)
                self.count += 1
            except self.gcode.error as e:
                error_message = str(e)
                break
            except:
                logging.exception("virtual_sdcard dispatch")
                break
            self.cmd_from_sd = False
            self.file_position = self.next_file_position
            # Do we need to skip around?
            if self.next_file_position != next_file_position:
                try:
                    self.current_file.seek(self.file_position)
                except:
                    logging.exception("virtual_sdcard seek")
                    self.work_timer = None
                    return self.reactor.NEVER
                lines = []
                partial_input = ""
        logging.info("Exiting SD card print (position %d)", self.file_position)

        if enable_delay_photography:
            try:
                # outfile = f"timelapse_{gcodefilename}_{date_time}{filename_extend}"
                from datetime import datetime
                now = datetime.now()
                date_time = now.strftime("%Y%m%d_%H%M")
                # 20220121010735@False@1@15@.mp4
                camera_site = True if timelapse_postion == 1 else False
                # filename_extend = f"@{camera_site}@{frequency}@{output_framerate}@"
                play_times = int(layer_count / int(frequency) / output_framerate)
                filename_extend = "@%s@%s@%s@%s@" % (camera_site, frequency, output_framerate, play_times)
                outfile = "timelapse_%s_%s%s" % (filename, date_time, filename_extend)
                rendering_video_cmd = """ffmpeg -framerate {0} -i  {1} -vcodec copy -y -f mp4 {2}.mp4""".format(
                    output_framerate, base_shoot_path, output_pre_video_path + "/" + outfile)
                logging.info(rendering_video_cmd)
                os.system(rendering_video_cmd)
                preview_jpg_path = test_jpg_path.replace("test.jpg", outfile + ".jpg")
                preview_jpg_cmd = "mv %s %s" % (test_jpg_path, preview_jpg_path)
                logging.info(preview_jpg_cmd)
                os.system(preview_jpg_cmd)
            except Exception as e:
                logging.exception(e)
                pass

        import threading
        t = threading.Thread(target=self._upload_remote_log)
        t.start()
        self.count = 0
        state = {}
        if os.path.exists(path):
            os.remove(path)

        self.work_timer = None
        self.cmd_from_sd = False
        if error_message is not None:
            self.print_stats.note_error(error_message)
            # import threading
            # t = threading.Thread(target=self._last_reset_file)
            # t.start()
        elif self.current_file is not None:
            self.print_stats.note_pause()
        else:
            self.print_stats.note_complete()
            import threading
            t = threading.Thread(target=self._last_reset_file)
            t.start()
        return self.reactor.NEVER

    def _last_reset_file(self):
        logging.info("will use _last_rest_file after 5s...")
        import time
        time.sleep(5)
        logging.info("use _last_rest_file")
        self._reset_file()

    def get_yaml_info(self, _config_file=None):
        """
        read yaml file info
        """
        import yaml
        # if not _config_file:
        if not os.path.exists(_config_file):
            return {}
        config_data = {}
        try:
            with open(_config_file, 'r') as f:
                config_data = yaml.load(f.read(), Loader=yaml.Loader)
        except Exception as err:
            pass
        return config_data

    def set_yaml_info(self, _config_file=None, data=None):
        """
        write yaml file info
        """
        import yaml
        if not _config_file:
            return
        try:
            with open(_config_file, 'w+') as f:
                yaml.dump(data, f, allow_unicode=True)
                f.flush()
            os.system("sync")
        except Exception as e:
            pass

    def _upload_remote_log(self):
        if self.printer.in_shutdown_state:
                return
        import urllib2
        # if os.path.exists("/etc/init.d/klipper_service.2"):
        #     # multiprinter.yaml
        #     MULTI_PRINTER_PATH = "/mnt/UDISK/.crealityprint/multiprinter.yaml"
        #     multi_printer_info = self.get_yaml_info(MULTI_PRINTER_PATH)
        #     multi_printer_info_list = multi_printer_info.get("multi_printer_info")
        #     for printer_info in multi_printer_info_list:
        #         if str(printer_info.get("printer_id")) == self.index:
        #             printer_info["status"] = 1
        #             self.set_yaml_info(MULTI_PRINTER_PATH, multi_printer_info)
        #             break
        with open("/mnt/UDISK/.crealityprint/printer%s_stat" % self.index, "w+") as f:
            f.write("1")
        response = urllib2.urlopen(
            "http://127.0.0.1:8000/settings/machine_info/?method=record_log_to_remote_server&message=print_exit_upload_log&index=%s" % self.index)

    def _upload_remote_log_start_print(self):
        import urllib2
        # if os.path.exists("/etc/init.d/klipper_service.2"):
        #     # multiprinter.yaml
        #     MULTI_PRINTER_PATH = "/mnt/UDISK/.crealityprint/multiprinter.yaml"
        #     multi_printer_info = self.get_yaml_info(MULTI_PRINTER_PATH)
        #     multi_printer_info_list = multi_printer_info.get("multi_printer_info")
        #     for printer_info in multi_printer_info_list:
        #         if str(printer_info.get("printer_id")) == self.index:
        #             printer_info["status"] = 2
        #             self.set_yaml_info(MULTI_PRINTER_PATH, multi_printer_info)
        #             break
        with open("/mnt/UDISK/.crealityprint/printer%s_stat" % self.index, "w+") as f:
            f.write("2")
        response = urllib2.urlopen(
            "http://127.0.0.1:8000/settings/machine_info/?method=record_log_to_remote_server&message=start_print&index=%s&filename=%s" % (self.index, self.current_file.name))

def load_config(config):
    return VirtualSD(config)
