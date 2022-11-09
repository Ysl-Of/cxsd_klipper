Welcome to the Klipper project!

[![Klipper](docs/img/klipper-logo-small.png)](https://www.klipper3d.org/)

https://www.klipper3d.org/

Klipper is a 3d-Printer firmware. It combines the power of a general
purpose computer with one or more micro-controllers. See the
[features document](https://www.klipper3d.org/Features.html) for more
information on why you should use Klipper.

To begin using Klipper start by
[installing](https://www.klipper3d.org/Installation.html) it.

Klipper is Free Software. See the [license](COPYING) or read the
[documentation](https://www.klipper3d.org/Overview.html).

#### V0.1.1
1. klipper默认日志级别改为INFO
2. 新增打印机断连堆栈日志
#### V0.0.80
1. 多机控制-打印机状态设置（断联、空闲、正在打印）
2. Z轴校准判断提示兼容多台打印机模式
#### V0.0.74
1.z轴校准保存Z轴补偿值,优化数值范围判断的弹窗问题;
2.新增配置选项必须添加的报错翻译Key
#### V0.0.71
1.z轴校准时,z轴偏移为正数时,提示其保存的范围不对;
2.修复code码为空的翻译报错;
3.key171翻译报错bug修复;
#### V0.0.65
1. 修复振动补偿翻译报错bug;
2. 修复key1的翻译报错bug;
#### V0.0.62
1. 摄像头断连不发送延迟摄影指令;
2. 修复打印时字符编码报错;
3. 修复 key0 的翻译返回错误bug;
#### V0.0.59
1. MCU_trsync类和mcu_pwm类相关报错新增翻译key;
#### V0.0.58
1. 修复交换config发送指令异常bug;
2. 修改日志保存策略,每个20M，最多5个;
#### V0.0.55
1. 添加bltouch探针z_offset设置错误提示;
2. 修复bltouch最小值报错时没有改为touch显示bug;
3. 保存变量异常报错翻译补充;
4. 打印机未准备报错新增翻译key;
#### V0.0.47
1. _get_wrapper函数klipper配置项报错翻译新增key;
#### V0.0.44
1. invoke_shutdown上报日志细节改动;
2. saveconfig命令增加sync操作，防止断电丢失配置文件;
3. 线程处理打印机断连记录;
4. klipper固件打印完成后触发上报日志;
#### V0.0.39
1. 打印机连接和断连上报日志;
2. 日志模块增加格式化信息包括日期、日志等级、代码函数名、line等信息;
#### V0.0.36
1. bltouch报z_offset错误时返回值改为touch, 新增翻译key;
2. 配置相关报错翻译key;
3. htu21d报错翻译key;
4. manual_probe报错翻译key;
5. probe报错翻译key;
6. replicape报错翻译key;
#### V0.0.31
1. 开机添加timelapse.cfg配置文件;
2. Manual probe failed错误从respond_info级别改为error;
3. adxl345无效速率参数错误翻译key补充;
4. 热床选项设置值最大最小无效参数等错误翻译key补充;
5. gcode具体指令参数值报错翻译key补充;
#### V0.0.27
1. 添加挤出过长,请检查选项值的翻译key值;
2. move_error错误修改翻译key值;
3. 显示报错、mcu报错补充、hd44780补充、menu_keys补充、print_stats补充、st7920补充、打印报错补充新增翻译key;
4. pwm、调平点位、QuadGantryLevel、SD卡、暂停与恢复、LM75、htu21d、宏定义
、adc_scaled、menu_key、manual_stepper、manual_probe翻译报错新增key;
#### V0.0.21
1.解决打印机固件连接中断时返回json格式异常问题;
2.屏蔽延迟摄影喷头拍摄移开功能;
#### V0.0.17
1.延迟摄影移开喷头位置拍摄实现;
2.adxl345、喷头步进器管理、通讯协议、打印等异常报错翻译新增key;
3.手动调平、cartesian、corexy、风扇、gcode解析、喷头、mcu、压力传感器、spi_flash、步进电机翻译报错新增key;
#### V0.0.13
1.自动调平、轴加速器、mux命令报错翻译新增key;
2.温度检测、振动补偿、归位异常报错翻译新增key值;
3.目标设定温度超出范围报错key,value,msg数据json格式返回;
#### V0.0.9
1. klipper添加requirements.txt;
2. 报错信息新增key值;
3. 打印机准备中提示新增key值;
4. 延迟摄影按层打印;
5. 按层打印的注释替换TAKE_NEW_FRAME记录到日志;
6. PyYAML库替换为3.11版本;

### Test