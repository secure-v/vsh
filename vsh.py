#!/usr/bin/python3

# ====================================================================================================
#  VSH: SHell for Visualizing vcd file                                                              ||
#  Copyleft (C) Clayden University                                                                 ||
#  License GPLv3: GNU GPL version 3                                                                 ||
#  Author: Fu-yao                                                                                   ||
#  Bug report & maintainer: fuyao-cu@outlook.com                                                    ||
#  VSH is open source and freely distributable                                                      ||
# ====================================================================================================

import os
import sys
import struct
import bisect
import random
import datetime
from enum import Enum
from pyDigitalWaveTools.vcd.parser import VcdParser
from pyDigitalWaveTools.vcd.common import VcdVarScope
from pyDigitalWaveTools.vcd.parser import VcdVarParsingInfo

import cmd2
from cmd2 import Cmd2ArgumentParser, with_argparser

from cmd2 import (
    Bg,
    Fg,
    style,
)

from capstone import *

search_var_list = [] # the global list of signal name (while using search cmd)

# -------------------------------- expression evaluation -------------------------------- #
operator_precedence = {
    # "-" :   2,
    # "!" :   2,
    # "~" :   2,
    "/" :   3,
    "*" :   3,
    "%" :   3,
    "+" :   4,
    "-" :   4,
    "<<":   5,
    ">>":   5,
    ">=":   6,
    ">" :   6,
    "<=":   6,
    "<" :   6,
    "==":   7,
    "!=":   7,
    "^" :   9,
    "||":  12,
    "|" :  10,
    "&&":  11,
    "&" :   8,
}


class expr_eval:
    def __init__(self):
        self.op = None # ?: signal name (var)
        self.val1 = None
        self.val2 = None
        self.var_val_dict = None
        
        return

    def set_var_val_dict(self, vvd):
        self.var_val_dict = vvd

        return 
    
    def parse(self, expr):
        expr = expr.lstrip().rstrip()
        nest_bracket = []
        nest_level = 0

        for i in expr:
            if i == '(':
                nest_level += 1
                nest_bracket.append(nest_level)
                
            elif i == ')':
                nest_bracket.append(nest_level)
                nest_level -= 1
            else:
                nest_bracket.append(nest_level)

        if nest_level != 0:
            print("Invalid expression:", expr)

            return
        
        flag = False

        for i in nest_bracket:
            if i == 0:
                flag = True
                break

        if flag == False: # eg: "(1+2)"
            self.parse(expr[1:-1])

            return
        
        min_op_index = 0
        min_op_precedence = 0
        i = 1 # skip the first item (not binary operator)
        cur_expr_op = ""

        while i < (len(nest_bracket) - 1): # cannot find op at the end of a valid expression, eg: 1+2-
            if nest_bracket[i] == 0:
                for (k, v) in operator_precedence.items():
                    if k == expr[i:i + 2]: # match "==" ">=" etc
                        if min_op_precedence <= v:
                            min_op_index = i
                            min_op_precedence = v
                            self.op = k
                            cur_expr_op = k

                        i += 1

                        break
                    elif k == expr[i]: # match "-" "+" etc
                        if min_op_precedence <= v:
                            min_op_index = i
                            min_op_precedence = v
                            self.op = k
                            cur_expr_op = k

                        break

            i += 1
        
        if min_op_precedence == 0:
            if expr[0:2] == "0x":
                if expr[2] == 'x' or expr[2] == 'z':
                    self.val2 = expr[2]
                else:
                    self.val2 = int(expr, 16) # need assert when fail
            elif expr[0:2] == "0b":
                if expr[2] == 'x' or expr[2] == 'z':
                    self.val2 = expr[2]
                else:
                    self.val2 = int(expr, 2) # need assert when fail
            elif expr[0:2] == "0o":
                if expr[2] == 'x' or expr[2] == 'z':
                    self.val2 = expr[2]
                else:
                    self.val2 = int(expr, 8) # need assert when fail
            elif expr[0] >= '0' and expr[0] <= '9': # number
                for i in expr:
                    if i >= '0' and i <= '9':
                        continue
                    else:
                        print("Invalid expression:", expr)
                        return
        
                self.val2 = int(expr)
            elif expr[0] == "-" or expr[0] == "!" or expr[0] == "~":
                self.op = expr[0]
                child = expr_eval()
                child.parse(expr[1:])
                self.val2 = child

                return
            else: # signal name
                self.op = "?"
                self.val2 = expr
                global search_var_list
                search_var_list.append(expr)

            return
        
        child1 = expr_eval()
        child1.parse(expr[0:min_op_index])
        self.val1 = child1

        child2 = expr_eval()
        child2.parse(expr[min_op_index + len(cur_expr_op):])
        self.val2 = child2

        return 

    def eval(self):
        if self.op == None and self.val2 == None:
            print("Invalid expression!")
            return 
        
        if self.op == None:
            return self.val2
        
        if self.op == "?":
            return self.var_val_dict[self.val2]
        
        self.val2.set_var_val_dict(self.var_val_dict)
        opr =  self.val2.eval()

        if opr == None:
            print("Invalid expression!")
            return
        
        if self.val1 == None: # unary
            if self.op == '-':
                return -opr
            elif self.op == '~':
                return ~opr
            elif self.op == '!':
                return not opr
        
        self.val1.set_var_val_dict(self.var_val_dict)
        opl = self.val1.eval()

        if opl == None:
            print("Invalid expression!")
            return
        
        res = 0

        if self.op == '/':
            res = int(opl / opr)
        elif self.op == '*':
            res = opl * opr
        elif self.op == '%':
            res = opl % opr
        elif self.op == '+':
            res = opl + opr
        elif self.op == '-':
            res = opl - opr
        elif self.op == '<<':
            res = opl << opr
        elif self.op == '>>':
            res = opl >> opr
        elif self.op == '<':
            res = opl < opr
        elif self.op == '<=':
            res = opl <= opr
        elif self.op == '>':
            res = opl > opr
        elif self.op == '>=':
            res = opl >= opr
        elif self.op == '==':
            res = opl == opr
        elif self.op == '!=':
            res = opl != opr
        elif self.op == '&':
            res = opl & opr
        elif self.op == '^':
            res = opl ^ opr
        elif self.op == '|':
            res = opl | opr
        elif self.op == '&&':
            res = opl and opr
        elif self.op == '||':
            res = opl or opr

        return res

# ======================================================================================= #

list_argparser = Cmd2ArgumentParser()
list_argparser.add_argument('-s', '--signal_list', action='store_true', help='list current signals under spying')
list_argparser.add_argument('-m', '--marker_list', action='store_true', help='list markers')
list_argparser.add_argument('word', nargs='?', help='path of submodule')

show_argparser = Cmd2ArgumentParser()
show_argparser.add_argument('-n', '--next', type=str, help='set the increment of t')
show_argparser.add_argument('word', nargs='?', help='signal name')

add_argparser = Cmd2ArgumentParser()
add_argparser.add_argument('-f', '--format', type=str, help='set display format of signal value')
add_argparser.add_argument('-fg', '--foreground', type=str, help='set foreground color')
add_argparser.add_argument('-fgr', '--foreground_random', action='store_true', help='set foreground to a random color')
add_argparser.add_argument('-bg', '--background', type=str, help='set background color')
add_argparser.add_argument('-bgr', '--background_random', action='store_true', help='set background to a random color')
add_argparser.add_argument('-m', '--mode', type=str, help='set display mode')
add_argparser.add_argument('word', nargs='?', help='signal name')

mg_argparser = Cmd2ArgumentParser()
mg_argparser.add_argument('-m', '--macro', type=str, help='macro set')
mg_argparser.add_argument('-v', '--value', type=str, help='macro value set')
mg_argparser.add_argument('-n', '--name', type=str, help='name of macro group')

bm_argparser = Cmd2ArgumentParser()
bm_argparser.add_argument('-n', '--name', type=str, help='name of macro group')
bm_argparser.add_argument('-s', '--signal_name', type=str, help='signal to bond')

bd_argparser = Cmd2ArgumentParser()
bd_argparser.add_argument('-s', '--signal_name', type=str, help='signal to bond')
bd_argparser.add_argument('-a', '--architecture', type=str, help='bond signal to disassembler with certain architecture')

disasm_argparser = Cmd2ArgumentParser()
disasm_argparser.add_argument('-a', '--architecture', type=str, help='set architecture')
disasm_argparser.add_argument('word', nargs='?', help='data')

color_argparser = Cmd2ArgumentParser()
color_argparser.add_argument('-fg', '--foreground', type=str, help='set foreground color')
color_argparser.add_argument('-fgr', '--foreground_random', action='store_true', help='set foreground to a random color')
color_argparser.add_argument('-bg', '--background', type=str, help='set background color')
color_argparser.add_argument('-bgr', '--background_random', action='store_true', help='set background to a random color')
color_argparser.add_argument('-m', '--mode', type=str, help='set display mode')
color_argparser.add_argument('-i', '--index', type=str, help='the index of the signal')
color_argparser.add_argument('word', nargs='?', help='signal name')

marker_argparser = Cmd2ArgumentParser()
marker_argparser.add_argument('-d', '--delete', action='store_true', help='delete the marker')
marker_argparser.add_argument('-l', '--list', action='store_true', help='list the markers')
marker_argparser.add_argument('-i', '--index', type=str, help='index of the marker')
marker_argparser.add_argument('-t', '--time', type=str, help='time of the marker')
marker_argparser.add_argument('-fg', '--foreground', type=str, help='set foreground color of the marker')
marker_argparser.add_argument('-fgr', '--foreground_random', action='store_true', help='set marker\'s foreground to a random color')
marker_argparser.add_argument('-bg', '--background', type=str, help='set background color of the marker')
marker_argparser.add_argument('-bgr', '--background_random', action='store_true', help='set marker\'s background to a random color')
marker_argparser.add_argument('-m', '--mode', type=str, help='set display mode of the marker')
marker_argparser.add_argument('word', nargs='?', help='marker name')

t_argparser = Cmd2ArgumentParser()
t_argparser.add_argument('-a', '--absolute', action='store_true', help='set value of the time point')
t_argparser.add_argument('word', nargs='?', help='marker name')

randc_argparser = Cmd2ArgumentParser()
randc_argparser.add_argument('-n', '--number', type=str, help='number of random color')

precision_argparser = Cmd2ArgumentParser()
precision_argparser.add_argument('word', nargs='?', help='precision')


icon = r"""======================================================================================================
||    ...@@@@@@@@@                                                               @                  ||
||     ......@@@@@@@@@@@@@                                                     @@@                  ||     
||      ........./     \@@@@@@@@@@                                           @@@@                   ||
||       ........|  O  |@@@@@@@@@@@@                                        @@@@@                   ||
||        .......\     /...@@@@@@@@@@@@@@@@                                 @@@@@@@@       @@@@@@   ||  
||          .......@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                         @@@@@@@@@@@@@@@@@@       ||    
||           .......@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@            || 
||             .......@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                       ||
||                 ......@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                              ||   
||                    ......@@@@@@@@.......@@@@@@@@@@@@@@@@@@@@@                                    ||
||                         @@@@@@@....                                                              ||
||                           @@@@@                                                                  ||
||                             @@@@                                                                 ||    
||                                @@                                                                ||
======================================================================================================
"""

info = """||                               SHell for Visualizing vcd file                                     ||
|| Copyright (C) %-4d Clayden University                                                            ||
|| License GPLv3: GNU GPL version 3                                                                 ||
|| Bug report & maintainer: fuyao-cu@outlook.com                                                    ||
|| VSH is open source and freely distributable                                                      ||
======================================================================================================""" % datetime.datetime.today().year



class DISP_FORMAT(Enum):
    b = 0
    o = 1
    d = 2
    h = 3
    f = 4 # float / double
    s = 5 # signed
    a = 6 # ascii
    m = 7 # machine code (disassemble result) / macro name


def render(strVal, *, fg = (255, 255, 255), bg = (0, 0, 0), mode = 0):
    if bg == None:
        res_str = f"\x1b[{mode}m\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m{strVal}\x1b[0m"
    else:
        res_str = f"\x1b[{mode}m\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m{strVal}\x1b[0m"
    
    return res_str


def str2num(numStr):
    val = None

    try:
        if numStr[0:2] == '0x':
            val = int(numStr[2:], 16)
        elif numStr[0:2] == '0b':
            val = int(numStr[2:], 2)
        elif numStr[0:2] == '0o':
            val = int(numStr[2:], 8)
        else:
            val = int(numStr)
        
        return val
    except Exception as e:
        print("Invalid number:", numStr)
        return None
    
    return val
    

class vsh(cmd2.Cmd):
    CUSTOM_CATEGORY = 'Custom Commands'
    def __init__(self):
        super().__init__(
            multiline_commands=['echo'],
            persistent_history_file='.vsh_history',
            startup_script='.vsh_start',
            include_ipy=True,
        )

        # self.intro = style(icon, fg=Fg.BLUE, bg=None, bold=True) + info
        self.intro = icon.replace('@', "\033[34m@\033[0m") + info
        self.prompt = 'vsh> '
        self.continuation_prompt = '... '
        self.self_in_py = True
        self.default_category = 'cmd2 Built-in Commands'
        self.foreground_color = Fg.CYAN.name.lower()
        self.vcd = VcdParser()
        self.cur_mod = None
        self.t = 0
        self.spy_sig_list = [] # [(VcdVarParsingInfo, time_val, format, color)]
        self.shadow_for_logic = False # do not show the signal value when wire length == 1

        self.CS_ARCH = CS_ARCH_RISCV
        self.CS_MODE = CS_MODE_RISCV64

        self.macro_map = {}
        self.marker_list = []

        self.max_t = None

        self.precision = 4

        fg_colors = [c.name.lower() for c in Fg]
        self.add_settable(
            cmd2.Settable('foreground_color', str, 'Foreground color to use with echo command', self, choices=fg_colors)
        )


    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_intro(self, _):
        """Display the intro banner"""
        print(self.intro)


    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_sfl(self, opts):
        """Display color bar for signal (wire length == 1)"""
        if opts == "0":
            self.shadow_for_logic = False
        else:
            self.shadow_for_logic = True
        
        return

    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_load(self, opts):
        if os.path.exists(opts) == False:
            print("No such vcd file:", opts)
            return

        with open(opts) as vcd_file:
            self.vcd = VcdParser()
            self.vcd.parse(vcd_file)

        self.prompt = "/ > "
        self.cur_mod = self.vcd.scope
        max_time_point = -1

        for sig in self.vcd.idcode2series.items():
            for i in sig[1]:
                if i[0] > max_time_point:
                    max_time_point = i[0]

        self.max_t = max_time_point
        
        ## reset values
        self.spy_sig_list = [] # [(VcdVarParsingInfo, time_val, format, color)]

    complete_load = cmd2.Cmd.path_complete


    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(list_argparser)
    def do_list(self, opts):
        if opts.signal_list:
            index_num = 0
            
            for i in self.spy_sig_list:
                mod = i[0].parent
                mod_hier = ""

                if mod.parent == None:
                    mod_hier = "/" + mod_hier

                while mod.parent != None:
                    mod_hier = "/" + mod.name + mod_hier
                    mod = mod.parent

                print((render(("%-4d %s %d %s" % (index_num, i[0].name, i[0].width, mod_hier)), fg = i[1][0], bg = i[1][1], mode = i[1][2])))
                index_num += 1
    
            return 

        if opts.marker_list:
            j = 0

            for i in self.marker_list:
                print("[%5d] %-20d: " % (j, i[1]) + render(i[0], fg = i[2][0], bg = i[2][1], mode = i[2][2]))
                j += 1

            return

        if self.cur_mod == None:
            return
        
        mod = self.cur_mod.children

        for k, v in mod.items():
            if isinstance(v, VcdVarParsingInfo):
                print("\033[32m%s\033[0m %d" % (v.name, v.width))
            elif isinstance(v, VcdVarScope):
                print("\033[34m%s\033[0m" % (v.name))

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(list_argparser)
    def do_l(self, opts):
        if opts.signal_list:
            index_num = 0
            
            for i in self.spy_sig_list:
                mod = i[0].parent
                mod_hier = ""

                if mod.parent == None:
                    mod_hier = "/" + mod_hier

                while mod.parent != None:
                    mod_hier = "/" + mod.name + mod_hier
                    mod = mod.parent

                print("%-4d" % index_num, i[0].name, i[0].width, mod_hier)
                index_num += 1

            return 

        if opts.marker_list:
            j = 0

            for i in self.marker_list:
                print("[%5d] %-20d: " % (j, i[1]) + render(i[0], fg = i[2][0], bg = i[2][1], mode = i[2][2]))
                j += 1

            return

        if self.cur_mod == None:
            return

        mod = self.cur_mod.children

        for k, v in mod.items():
            if isinstance(v, VcdVarParsingInfo):
                print("\033[32m%s\033[0m %d" % (v.name, v.width))
            elif isinstance(v, VcdVarScope):
                print("\033[34m%s\033[0m" % (v.name))
    
    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_pwm(self, opts):
        mod = self.cur_mod

        if mod == None:
            print("Please load vcd file.")
            return
        
        pwm = ""

        if mod.parent == None:
            pwm = "/" + pwm
                
        while mod.parent != None:
            pwm = "/" + mod.name + pwm
            mod = mod.parent

        print(pwm)
    
    def adjust_prompt(self):
        mod = self.cur_mod
        self.prompt = " > "

        if mod.parent == None:
            self.prompt = "/" + self.prompt
        
        while mod.parent != None:
            self.prompt = "/" + mod.name + self.prompt
            mod = mod.parent
        
        return
        
    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_cm(self, opts):
        if self.cur_mod == None:
            print("Please load vcd file.")
            return
        
        if opts == ".":
            return 
        elif opts == "..":
            mod = self.cur_mod

            if mod.parent != None:
                self.cur_mod = mod.parent
                self.adjust_prompt()
            
            return
        elif opts == "/":
            self.cur_mod = self.vcd.scope
            self.adjust_prompt()
            
            return

        if opts == None or opts == "":
            self.do_cm("/")

            return
        
        mod_children = self.cur_mod.children
        args = opts

        if opts[0] == '/': # absolute path
            mod_children = self.vcd.scope.children
            args = opts[1:]

        args_list = args.split('/')
        flag = True
        res_mod = self.cur_mod

        for i in args_list:
            for k, v in mod_children.items():
                flag = False
                
                if i == '.' or i == '':
                    mod_children = res_mod.children
                    flag = True
                    break
                elif i == '..':
                    if res_mod.parent != None:
                        res_mod = res_mod.parent
                    
                    mod_children = res_mod.children
                    flag = True
                    break
                elif v.name == i and isinstance(v, VcdVarScope):
                    mod_children = v.children
                    res_mod = v
                    flag = True
                    break
            
            if flag == False:
                break

        if flag == False:
            print("No such submodule:", opts)
        else:
            self.cur_mod = res_mod
            self.adjust_prompt()

        return 
    

    def complete_cm(self, text, line, begidx, endidx):
        complete_cm_list = []

        if self.cur_mod != None:
            for k, v in self.cur_mod.children.items():
                
                if isinstance(v, VcdVarScope):
                    complete_cm_list += [v.name]

        return self.basic_complete(text, line, begidx, endidx, complete_cm_list)
    

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(t_argparser)
    def do_t(self, opts):
        if (opts.word == "") or (opts.word == None):
            print("CURRENT_TIME / MAX_TIME:", self.t, "/", self.max_t)
            return 

        res = 0

        try:
            res = int(opts.word)
        except Exception as e:
            print (e, ": Wrong parameter")
            return
        
        if opts.absolute:
            self.t = res
        else:
            self.t += res

        if self.t < 0:
            self.t = 0
            
        if self.t > self.max_t:
            self.t = self.max_t

        print("CURRENT_TIME / MAX_TIME:", self.t, "/", self.max_t)

        return 

    def align_sig(self, side_w, max_sig_w, str_list, sig_width=None, fg = (255, 255, 255), bg = None, mode = 0):
        res = str_list[0].ljust(side_w, ' ')
        val_str_list = [(str_list[1], 1)]

        if self.shadow_for_logic and sig_width == 1:
            if bg == None:
                bg = (135, 170, 104) # WoW

            for i in str_list[1:]:
                if i == '1':
                    res += render(" " * max_sig_w, fg = fg, bg = bg, mode = mode)
                else:
                    res += render("_" * max_sig_w, fg = fg, bg = None, mode = mode)
            
            return res

        for i in range(2, len(str_list)):
            if str_list[i] == val_str_list[-1][0]:
                val_str_list[-1] = (val_str_list[-1][0], val_str_list[-1][1] + 1)
            else:
                val_str_list += [(str_list[i], 1)]

        for i in val_str_list:
            val_str = i[0].center(max_sig_w * i[1], ' ')
            res += "\\" + val_str[1:-1] + "/"

        # if sig_width == 1:
        #     for i in val_str_list:
        #         if i[0] == '1':
        #             res += "\e[44m \e[0m" * i[1]
        #         else:
        #             res += "\e[4m \e[0m" * i[1]
        # else:
        #     for i in val_str_list:
        #         val_str = i[0].center(max_sig_w * i[1], ' ')
        #         res += "\\" + val_str[1:-1] + "/"

        # for i in range(1, len(str_list)):
        #     val_str = str_list[i].center(max_sig_w, ' ')
        #     res += "\\" + val_str[1:-1] + "/"
        
        return res

    def search_val(self, tmax, time_val_list):
        index = bisect.bisect_right(time_val_list, self.t, hi = len(time_val_list), key = lambda X : X[0])
        
        if index == len(time_val_list):
            return [time_val_list[-1][1]] * tmax

        if time_val_list[index][0] > self.t:
            index -= 1
        
        res = []
        i = 0

        while i < tmax:
            if index == (len(time_val_list) - 1):
                res += [time_val_list[-1][1]] * (tmax - i)
                break
            
            if ((self.t + i) >= time_val_list[index][0]) and ((self.t + i) < time_val_list[index + 1][0]):
                res += [time_val_list[index][1]]
                i += 1
            elif self.t + i >= time_val_list[index + 1][0]:
                index += 1
        
        return res


    def bin2float(self, bstr):
        val = 0.0

        if len(bstr) == 32:
            val = struct.unpack('>f', struct.pack('>I', int(bstr, 2)))[0]
        elif len(bstr) == 64:
            val = struct.unpack('>d', struct.pack('>Q', int(bstr, 2)))[0]

        return val


    def bin2signed(self, bstr):
        val = -(2 ** (len(bstr) - 1))

        if bstr[0] == '0':
            val = 0

    
        val += int(bstr[1:], 2)

        return val


    def get_ascii_name(self, code):
        control_char = {
            0: "NUL",
            9: "HT",
            10: "LF",
            13: "CR",
            27: "ESC",
            32: "SPACE"
        }
    
        if 0 <= code <= 31:
            res = control_char.get(code)

            if res == None:
                res = f"\\0x{code:02X}"

            return res
        elif 33 <= code <= 126:
            return f"{chr(code)}"
        elif 127 <= code <= 255:
            return f"\\0x{code:02X}"
        else:
            return f"\\0x{code:02X}"

        return ""
    

    def digit_conv(self, val_list, fmt):
        res = []

        for i in val_list:
            bin_str = i
            val_str = ""

            if bin_str[0] == 'z' or bin_str[0] == 'x':
                res += [bin_str]
                continue

            if i[0] == 'b':
                bin_str = i[1:]

                if bin_str[0] == 'z' or bin_str[0] == 'x':
                    res += [bin_str]
                    continue

            if fmt == DISP_FORMAT.a:
                val_str = self.get_ascii_name(int(bin_str, 2))
            elif fmt == DISP_FORMAT.b:
                val_str = bin_str
            elif fmt == DISP_FORMAT.o:
                val_str = oct(int(bin_str, 2))[2:]
            elif fmt == DISP_FORMAT.d:
                val_str = "%d" % int(bin_str, 2)
            elif fmt == DISP_FORMAT.f:
                fval = self.bin2float(bin_str)
                val_str = f"{fval:.{self.precision}E}"
            elif fmt == DISP_FORMAT.s:
                sval = self.bin2signed(bin_str)
                val_str = "%d" % (sval)
            else: 
                val_str = hex(int(bin_str, 2))[2:]
            
            res += [val_str]
        
        return res

    
    def digit_to_instr(self, val_list, arch_mode):
        res = []

        for i in val_list:
            bin_str = i
            val_str = ""

            if bin_str[0] == 'z' or bin_str[0] == 'x':
                res += [bin_str]
                continue

            if i[0] == 'b':
                bin_str = i[1:]

                if bin_str[0] == 'z' or bin_str[0] == 'x':
                    res += [bin_str]
                    continue

            val_str = self.disasm_data(int(bin_str, 2), arch_mode)
            
            if (len(val_str) == 0): # invalid instruction
                res += [hex(int(bin_str, 2))[2:]]
            else:
                res += [val_str]
        
        return res


    def digital_to_macro(self, val_list, macro_map):
        res = []

        for i in val_list:
            bin_str = i
            val_str = ""

            if bin_str[0] == 'z' or bin_str[0] == 'x':
                res += [bin_str]
                continue

            if i[0] == 'b':
                bin_str = i[1:]

                if bin_str[0] == 'z' or bin_str[0] == 'x':
                    res += [bin_str]
                    continue

            val_str = macro_map.get(int(bin_str, 2))

            if (val_str == None):
                res += [hex(int(bin_str, 2))[2:]]
            else:
                res += [val_str]
        
        return res


    def disasm_data(self, value, arch_mode = None):
        value_bytes = value.to_bytes(length = 4, byteorder = 'little', signed = False)
        md = Cs(self.CS_ARCH, self.CS_MODE)

        if arch_mode:
            md = Cs(arch_mode[0], arch_mode[1])

        disasm_res = md.disasm(value_bytes, 0)
        res = ""

        for i in disasm_res: # the first instruction
            res = "%s %s" % (i.mnemonic, i.op_str)

            return res

        return res

    def show_sig(self):
        width = os.get_terminal_size().columns
        height = os.get_terminal_size().lines
        side_w = len("T=%d" % self.t)
        

        for i in self.spy_sig_list:
            name_w = len(i[0].name)

            if name_w > side_w:
                side_w = name_w
        

        for j in self.marker_list:
            marker_w = len(j[0])

            if marker_w > side_w:
                side_w = marker_w


        max_sig_w = 4

        for i in self.spy_sig_list:
            sig_w = 0

            if isinstance (i[3], tuple): # need disasm
                sig_w = 24
            elif isinstance (i[3], dict): # macro dict
                sig_w = max([len(p) for p in i[3].values()])
            elif i[2] == DISP_FORMAT.a:
                sig_w = i[0].width + 2
            elif i[2] == DISP_FORMAT.b:
                sig_w = i[0].width + 2
            elif i[2] == DISP_FORMAT.o or i[2] == DISP_FORMAT.d:
                sig_w = int((i[0].width + 2) / 3) + 2
            else: # signed / float / others
                sig_w = ((i[0].width + 3) >> 2) + 2

            if sig_w > max_sig_w:
                max_sig_w = sig_w
        
        side_w += 3

        if (side_w + max_sig_w) > width:
            print("The terminal is too small: %d X %d, width >= %d is required." % (width, height, side_w + max_sig_w))

            return 

        tmax = int((width - side_w) / max_sig_w)
        t_list = ["T=%d" % self.t]

        for i in range(tmax):
            t_list += ["%d" % i]
        
        # display the title (T)
        t_str = self.align_sig(side_w, max_sig_w, t_list, (255, 255, 255), None, 0)
        print("-" * len(t_str))
        print(t_str)
        print("-" * len(t_str))

        # display the signal
        for i in self.spy_sig_list:
            v = i[0]
            sig_time_val_list = None
            sfl_tmp = self.shadow_for_logic

            if isinstance(v.vcdId, list):
                sig_time_val_list = v.vcdId
            elif isinstance(v.vcdId, str):
                sig_time_val_list = self.vcd.idcode2series[v.vcdId]

            val_list = self.search_val(tmax, sig_time_val_list)
            fmt = i[2]
            
            if isinstance (i[3], tuple): # need disasm
                val_list = self.digit_to_instr(val_list, i[3])
            elif isinstance (i[3], dict): # macro dict
                self.shadow_for_logic = False
                val_list = self.digital_to_macro(val_list, i[3])
            else:
                val_list = self.digit_conv(val_list, fmt)

            suffix = '[H]'
            
            if fmt == DISP_FORMAT.a:
                suffix = '[A]'
            elif fmt == DISP_FORMAT.b:
                suffix = '[B]'
            elif fmt == DISP_FORMAT.o:
                suffix = '[O]'
            elif fmt == DISP_FORMAT.d:
                suffix = '[D]'
            elif fmt == DISP_FORMAT.f:
                suffix = '[F]'
            elif fmt == DISP_FORMAT.s:
                suffix = '[S]'
            elif fmt == DISP_FORMAT.m:
                suffix = '[M]'

            sig_str = self.align_sig(side_w, max_sig_w, [v.name + suffix] + val_list, v.width, i[1][0], i[1][1], i[1][2])
            self.shadow_for_logic = sfl_tmp
            # print(style(sig_str, fg=i[1][0], bg=i[1][1], bold=i[1][2]))
            print(render(sig_str, fg = i[1][0], bg = i[1][1], mode = i[1][2]))

        print("=" * len(t_str))

        # display the marker
        marker_display_list = []

        for i in range((len(t_list))):
            for j in self.marker_list:
                if j[1] == i + self.t:
                    marker_display_list += [(i, j)]

        marker_output_str_list = [] # [(string0, current_layer0), ..., (stringN, current_layerN)]

        for i in marker_display_list:
            if i[0] == 0:
                marker_output_str_list += [(" " * side_w + render("\\", fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), 0)]
                marker_output_str_list += [(" " * side_w + render("|", fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), 0)]
                marker_output_str_list += [(render(i[1][0], fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]) + " " + render("-" * (side_w - len(i[1][0])), fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), 0)]
            elif i[0] == (len(t_list) - 1):
                for k in range(len(marker_output_str_list)):
                    append_str = "/"

                    if k != 0:
                        append_str = "|"
                    
                    marker_output_str_list[k] = (marker_output_str_list[k][0] + " " * ((max_sig_w * (i[0] - marker_output_str_list[k][1]) - 2)) + render(append_str, fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), i[0])
                    
                marker_output_str_list += [(render(i[1][0], fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]) + " " + render("-" * (side_w  + max_sig_w * i[0] - len(i[1][0]) - 1), fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), i[0])]
            else:
                for k in range(len(marker_output_str_list)):
                    append_str = "/\\"

                    if k != 0:
                        append_str = "||"
                    
                    marker_output_str_list[k] = (marker_output_str_list[k][0] + " " * ((max_sig_w * (i[0] - marker_output_str_list[k][1]) - 2)) + render(append_str, fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), i[0])
                    
                marker_output_str_list += [(render(i[1][0], fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]) + " " + render("-" * (side_w  + max_sig_w * i[0] - len(i[1][0])), fg = i[1][2][0], bg = i[1][2][1], mode = i[1][2][2]), i[0])]

        for i in marker_output_str_list:
            print(i[0])

        return 

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(show_argparser)
    def do_show(self, opts):
        if len(self.spy_sig_list) == 0:
            print("Please adding signal to display (T=%d)." % self.t)
            return
        
        if opts.next:
            val = 0
            try:
                val = int(opts.next)
            except Exception as e:
                print (e, ": Wrong parameter")
                return
    
            self.t += val

            if self.t < 0:
                self.t = 0
            
            if self.t > self.max_t:
                self.t = self.max_t

        self.show_sig()

        return 


    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(add_argparser)
    def do_add(self, opts):
        if opts.word == "":
            return 

        mod = self.cur_mod.children
        
        fmt = DISP_FORMAT.h
        foreground = (255, 255, 255)
        background = None
        mode = 0
        
        if opts.format == "a" or opts.format == "A" or opts.format == "ascii" or opts.format == "ASCII":
            fmt = DISP_FORMAT.a
        elif opts.format == "b" or opts.format == "B" or opts.format == "bin" or opts.format == "BIN":
            fmt = DISP_FORMAT.b
        elif opts.format == "o" or opts.format == "O" or opts.format == "oct" or opts.format == "OCT":
            fmt = DISP_FORMAT.o
        elif opts.format == "d" or opts.format == "D" or opts.format == "dec" or opts.format == "DEC":
            fmt = DISP_FORMAT.d
        elif opts.format == "h" or opts.format == "H" or opts.format == "hex" or opts.format == "HEX":
            fmt = DISP_FORMAT.h
        elif opts.format == "f" or opts.format == "F" or opts.format == "float" or opts.format == "FLOAT":
            fmt = DISP_FORMAT.f
        elif opts.format == "s" or opts.format == "S" or opts.format == "signed" or opts.format == "SIGNED":
            fmt = DISP_FORMAT.s
        elif opts.format == "" or opts.format == None:
            fmt = DISP_FORMAT.h
        else:
            print("Error format:", opts.format)
            return

        if opts.foreground:
            fgVal = str2num(opts.foreground)

            if fgVal == None:
                return 

            foreground = ((fgVal >> 16) & 255, (fgVal >> 8) & 255, (fgVal >> 0) & 255)
        
        if opts.background:
            bgVal = str2num(opts.background)
        
            if bgVal == None:
                return 

            background = ((bgVal >> 16) & 255, (bgVal >> 8) & 255, (bgVal >> 0) & 255)

        # random option overwrite the color setting value
        if opts.foreground_random:
            foreground = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            
        if opts.background_random:
            background = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

        if opts.mode:
            modeVal = str2num(opts.mode)

            if modeVal == None:
                return 

            mode = modeVal
            

        if opts.word == "*":
            for k, v in mod.items():
                if isinstance(v, VcdVarParsingInfo):
                    # (signal_object, (foreground_color, background_color, mode), macro_dictionary)
                    self.spy_sig_list += [(v, (foreground, background, mode), fmt, None)]
            
            return

        for k, v in mod.items():
            if v.name == opts.word and isinstance(v, VcdVarParsingInfo):
                self.spy_sig_list += [(v, (foreground, background, mode), fmt, None)]
                
        return 
    

    def complete_add(self, text, line, begidx, endidx):
        complete_add_list = []

        if self.cur_mod != None:
            for k, v in self.cur_mod.children.items():
                
                if isinstance(v, VcdVarParsingInfo):
                    complete_add_list += [v.name]

        return self.basic_complete(text, line, begidx, endidx, complete_add_list)

    
    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(randc_argparser)
    def do_randc(self, opts):
        color_number = 1

        if opts.number != None:
            color_number = str2num(opts.number)

        if color_number == None:
            color_number = 1
        
        if color_number < 0:
            color_number = 1
        
        if color_number > 100:
            color_number = 99
            print("[Warning] Exceed the limit of number (<= 100), set number as 100.")

        for i in range(color_number):
            colorVal = random.randint(0, 256 * 256 * 256 - 1)
            print("%2d. " % (i) + render("    ", bg = (((colorVal >> 16) & 255, (colorVal >> 8) & 255, (colorVal >> 0) & 255))) + " 0x%06x" % colorVal)
            
        return
    

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(precision_argparser)
    def do_precision(self, opts):
        self.precision = str2num(opts.word)

        return 

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(color_argparser)
    def do_color(self, opts):
        foreground = None
        background = None
        mode = None
        index_list = []
        index = None

        if opts.index:
            index = str2num(opts.index)

            if index == None:
                return 
            
            foreground = self.spy_sig_list[index][1][0]
            background = self.spy_sig_list[index][1][1]
            mode = self.spy_sig_list[index][1][2]
        elif opts.word:
            j = 0

            for i in self.spy_sig_list:
                if i[0].name == opts.word:
                    index_list += [j]
                
                j = j + 1
            
            if len(index_list) == 0:
                print("Need the correct name of signal!")
                return
        else:
            print("Need index of the signal to change its color!")
            return

        if opts.foreground_random:
            foreground = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        elif opts.foreground:
            fgVal = str2num(opts.foreground)

            if fgVal == None:
                return 

            foreground = ((fgVal >> 16) & 255, (fgVal >> 8) & 255, (fgVal >> 0) & 255)
        
        if opts.background_random:
            background = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        elif opts.background:
            bgVal = str2num(opts.background)
        
            if bgVal == None:
                return 

            background = ((bgVal >> 16) & 255, (bgVal >> 8) & 255, (bgVal >> 0) & 255)

        if opts.mode:
            modeVal = str2num(opts.mode)

            if modeVal == None:
                return 

            mode = modeVal

        if index != None:
            self.spy_sig_list[index] = (self.spy_sig_list[index][0], (foreground, background, mode), self.spy_sig_list[index][2], self.spy_sig_list[index][3])

        for index in index_list:
            if foreground == None:
                foreground = self.spy_sig_list[index][1][0]

            if background == None:
                background = self.spy_sig_list[index][1][1]
            
            if mode == None:
                mode = self.spy_sig_list[index][1][2]

            self.spy_sig_list[index] = (self.spy_sig_list[index][0], (foreground, background, mode), self.spy_sig_list[index][2], self.spy_sig_list[index][3])

        return 


    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(marker_argparser)
    def do_marker(self, opts):
        index = None
        time = None
        index_list = []

        if opts.index:
            index = str2num(opts.index)

            if index == None:
                return 

        if opts.time:
            time = str2num(opts.time)

        j = 0

        for i in self.marker_list:
            if i[0] == opts.word:
                index_list += [j]
            
            j = j + 1
        
        if index != None:
            index_list += [index]

        index_list.sort(reverse = True)

        if opts.delete:
            for index in index_list:
                if 0 <= index < len(self.marker_list):
                    del self.marker_list[index]

            return 

        if opts.time:
            ## !!! copy & paste
            foreground = (255, 255, 0)
            background = None
            mode = 0

            if opts.foreground_random:
                foreground = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            elif opts.foreground:
                fgVal = str2num(opts.foreground)

                if fgVal == None:
                    return 

                foreground = ((fgVal >> 16) & 255, (fgVal >> 8) & 255, (fgVal >> 0) & 255)

            if opts.background_random:
                background = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            elif opts.background:
                bgVal = str2num(opts.background)

                if bgVal == None:
                    return 

                background = ((bgVal >> 16) & 255, (bgVal >> 8) & 255, (bgVal >> 0) & 255)

            if opts.mode:
                modeVal = str2num(opts.mode)

                if modeVal == None:
                    return 
            ## !!! copy & paste

            mid = 0
            flag = False

            for mk in self.marker_list:
                if (mk[0] == opts.word) or (mk[1] == time):
                    flag = True
                    break

                mid = mid + 1

            if flag:
                self.marker_list[mid] = (opts.word, time, (foreground, background, mode)) # (name, time, (fg, bg, mode))
            else:
                self.marker_list += [(opts.word, time, (foreground, background, mode))] # (name, time, (fg, bg, mode))

        if opts.list or ((opts.index == None) and ((opts.word == None) or (opts.word == ""))):
            j = 0

            for i in self.marker_list:
                print("[%5d] %-20d: " % (j, i[1]) + render(i[0], fg = i[2][0], bg = i[2][1], mode = i[2][2]))
                j += 1


    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_del(self, opts):
        if opts == "":
            return 

        mod = self.cur_mod.children

        if opts == "*":
            self.spy_sig_list = []
            
            return
        
        new_list = []

        for i in self.spy_sig_list:
            if i[0].name != opts:
                new_list += [i]

        self.spy_sig_list = new_list

        return 


    def complete_del(self, text, line, begidx, endidx):
        complete_del_list = []

        for i in self.spy_sig_list:
            complete_del_list += [i[0].name]

        return self.basic_complete(text, line, begidx, endidx, complete_del_list)


    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_conv(self, opts): # convert number
        val = 0

        if opts.isdigit() == False:
            if len(opts) <= 2:
                print("Invalid number:", opts)
                return
            
            try:
                if opts[0:2] == '0x':
                    val = int(opts[2:], 16)
                elif opts[0:2] == '0b':
                    val = int(opts[2:], 2)
                elif opts[0:2] == '0o':
                    val = int(opts[2:], 8)
                else:
                    print("Invalid number:", opts)
                    return
            except Exception as e:
                print("Invalid number:", opts)
                return
        else:
            val = int(opts)

        print("BIN:", bin(val)[2:])
        print("OCT:", oct(val)[2:])
        print("DEC:", val)
        print("HEX:", hex(val)[2:])
                
        return 
    
    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_search(self, opts): # search condition
        if opts[0] == "\"":
            opts = opts[1:]

        if len(opts) < 1:
            print ("Invalid expression:", "\"")
            
        if opts[-1] == "\"":
            opts = opts[:-1]

        ex_ev = expr_eval()
        global search_var_list
        search_var_list = [] # clear the list
        ex_ev.parse(opts)

        if len(search_var_list) == 0: # no signal name in expression
            res = 0

            try:
                res = ex_ev.eval()
            except Exception as e:
                print ("Invalid expression:", opts)
                return

            if res != 0:
                print("[0, +inf)")
            
            return

        flag = False
        time_point_for_search = set()
        var_val_list_dict = dict()

        for i in search_var_list:
            flag = False

            for j in self.spy_sig_list:
                if j[0].name == i:
                    flag = True
                    sig_time_val_list = None

                    if isinstance(j[0].vcdId, list):
                        sig_time_val_list = j[0].vcdId
                    elif isinstance(j[0].vcdId, str):
                        sig_time_val_list = self.vcd.idcode2series[j[0].vcdId]

                    for k in sig_time_val_list:
                        time_point_for_search.add(k[0])
                    
                    var_val_list_dict[i] = sig_time_val_list
                    break
            
            if i == "@t" or i == "@T":
                continue
            
            if flag == False:
                print("Please add signal \"%s\" first." % (i))
                return

        begin_point = 0
        eval_nonzero = False
        res_field = []
        time_point_for_search = sorted(time_point_for_search)
        
        for i in time_point_for_search:
            var_val_dict = {} # var value in a certain time point
            var_val_dict["@t"] = i # @t == time point
            var_val_dict["@T"] = i

            for (k, v) in var_val_list_dict.items():
                index = bisect.bisect(v, i, hi = len(v), key = lambda X : X[0])

                if index == 0:
                    var_val_dict[k] = 0
                else:
                    bin_str = v[index  - 1][1]

                    if bin_str[0] == 'b':
                        bin_str = bin_str[1:]

                    if bin_str[0] == 'z' or bin_str[0] == 'x':
                        # print("Need to handle x and z in search, value name: %s!" % k)
                        var_val_dict[k] = bin_str[0]
                        continue

                    var_val_dict[k] = int(bin_str, 2)

            ex_ev.set_var_val_dict(var_val_dict)
            eval_res = ex_ev.eval()
            
            if eval_res != 0: # satisfy
                if eval_nonzero == False:
                    eval_nonzero = True
                    begin_point = i
            else: # eval_res == 0
                if eval_nonzero == True:
                    res_field.append((begin_point, i))
                    eval_nonzero = False

        if eval_nonzero == True:
            res_field.append((begin_point, -1)) # begin_point, +inf

        print_str = ""

        for i in res_field:
            bp = i[0]
            ep = i[1]

            if ep != -1:
                print_str += "[%d, %d) " % (bp, ep)
            else:
                print_str += "[%d, +inf)" % (bp)

        print(print_str)

        return 
    
    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_s(self, opts): # search condition
        self.do_search(opts)

        return 

    
    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_reorder(self, opts):
        new_order_str = opts.split(" ")
        spy_list_len = len(self.spy_sig_list)
        new_order_num = []
        ori_order_num = [i for i in range(spy_list_len)]

        for i in new_order_str:
            try:
                val = int(i)

                if val < -spy_list_len or val >= spy_list_len:
                    print("Argument out of index:", i)

                    return 

                new_order_num.append(val)
                ori_order_num[val] = spy_list_len
            except Exception as e:
                print(e, ": Wrong parameter")

                return

        
        for i in ori_order_num:
            if i != spy_list_len:
                new_order_num.append(i)
        
        new_spy_sig_list = []

        for i in new_order_num:
            new_spy_sig_list.append(self.spy_sig_list[i])
        
        self.spy_sig_list = new_spy_sig_list
        return 


    def str_to_int(self, val_str):
        val = 0

        if val_str.isdigit() == False:
            if len(val_str) <= 2:
                print("Invalid number:", val_str)
                return
            
            try:
                if val_str[0:2] == '0x':
                    val = int(val_str[2:], 16)
                elif val_str[0:2] == '0b':
                    val = int(val_str[2:], 2)
                elif val_str[0:2] == '0o':
                    val = int(val_str[2:], 8)
                else:
                    print("Invalid number:", val_str)
                    return
            except Exception as e:
                print("Invalid number:", val_str)
                return
        else:
            val = int(val_str)

        return val


    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(mg_argparser)
    def do_mg(self, opts):
        macro_list = opts.macro.split('&')
        macro_value = opts.value.split('&')

        if len(macro_list) != len(macro_value):
            print("Mismatch macro and value!")

            return 
        elif len(macro_list) == 0:
            print("No macro:", opts.macro)

            return 

        value_list = []

        for i in macro_value:
            value_list += [self.str_to_int(i)]
        
        if len(macro_list) != len(value_list):
            print("Mismatch macro and value!")

            return 
        
        self.macro_map[opts.name] = {}

        for i, j in zip(macro_list, value_list):
            self.macro_map[opts.name][j] = i

        print(opts.name, ":", self.macro_map[opts.name])

        return 

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(bm_argparser)
    def do_bm(self, opts):
        if self.macro_map.get(opts.name) == None:
            print("No such macro group:", opts.name)

            return 

        index = 0
        bm_index_list = []

        for i in self.spy_sig_list:
            if i[0].name == opts.signal_name:
                bm_index_list += [index]
            
            index += 1
        
        for i in bm_index_list:
            self.spy_sig_list[i] = self.spy_sig_list[i][:2] + (DISP_FORMAT.m, self.macro_map[opts.name], ) + self.spy_sig_list[i][4:]
            print(i, ":", opts.signal_name, "<>", opts.name)

        if len(bm_index_list) == 0:
            print("No such signal:", opts.signal_name)

        return 
    
    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(bd_argparser)
    def do_bd(self, opts):
        cs_arch = 0
        cs_mode = 0
        
        if opts.architecture == 'rv32' or opts.architecture == 'RV32':
            cs_arch = CS_ARCH_RISCV
            cs_mode = CS_MODE_RISCV32
        elif opts.architecture == 'rv64' or opts.architecture == 'RV64':
            cs_arch = CS_ARCH_RISCV
            cs_mode = CS_MODE_RISCV64
        else:
            print("Not support such architecture:", opts.architecture)

            return 

        index = 0
        bm_index_list = []

        for i in self.spy_sig_list:
            if i[0].name == opts.signal_name:
                bm_index_list += [index]
            
            index += 1
        
        for i in bm_index_list:
            self.spy_sig_list[i] = self.spy_sig_list[i][:2] + (DISP_FORMAT.m, (cs_arch, cs_mode), ) + self.spy_sig_list[i][4:]
            print(i, ":", opts.signal_name, "<>", opts.architecture)

        if len(bm_index_list) == 0:
            print("No such signal:", opts.signal_name)

        return 
    

    @cmd2.with_category(CUSTOM_CATEGORY)
    @with_argparser(disasm_argparser)
    def do_disasm(self, opts):
        val = 0
        cs_mode = self.CS_MODE
        cs_arch = self.CS_ARCH
        
        if opts.word.isdigit() == False:
            if len(opts.word) <= 2:
                print("Invalid input:", opts.word)
                return
            
            try:
                if opts.word[0:2] == '0x':
                    val = int(opts.word[2:], 16)
                elif opts.word[0:2] == '0b':
                    val = int(opts.word[2:], 2)
                elif opts.word[0:2] == '0o':
                    val = int(opts.word[2:], 8)
                else:
                    print("Invalid input:", opts.word)
                    return
            except Exception as e:
                print("Invalid input:", opts.word)
                return
        else:
            val = int(opts.word)
        
        if opts.architecture == "rv32" or opts.architecture == "RV32": 
            self.CS_ARCH = CS_ARCH_RISCV
            self.CS_MODE = CS_MODE_RISCV32
        elif opts.architecture == "rv64" or opts.architecture == "RV64": 
            self.CS_ARCH = CS_ARCH_RISCV
            self.CS_MODE = CS_MODE_RISCV64

        instr = self.disasm_data(val)
        self.CS_MODE = cs_mode
        self.CS_ARCH = cs_arch
        print(instr)

        return
#########################################################################    
    @cmd2.with_category(CUSTOM_CATEGORY)
    def do_exit(self, opts):
        sys.exit(0)
    
    @cmd2.with_category(CUSTOM_CATEGORY) # alias exit
    def do_e(self, opts):
        self.do_exit(opts)
    
    @cmd2.with_category(CUSTOM_CATEGORY) # alias exit
    def do_quit(self, opts):
        self.do_exit(opts)
    
    @cmd2.with_category(CUSTOM_CATEGORY) # alias exit
    def do_q(self, opts):
        self.do_exit(opts)


if __name__ == '__main__':
    app = vsh()
    # app.onecmd("alias create save history \"|\" sed \'s/^ *[0-9]*[ ]*//\' \">\" .vsh_start_$(date +\"%Y_%m_%d_%H_%M_%S\")")
    # app.onecmd("alias create n show -n 1")
    # app.onecmd("alias create p show -n -1")
    app.cmdloop()
