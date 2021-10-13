import tkinter as tk
import re
import os
from tkinter import ttk
from tk_tools import Led
import queue
import threading
import u6
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from scipy.signal import savgol_filter
from LabJackPython import LabJackException

class ThreadedTask():
    def __init__(self, master, func, *args, **kwargs):
        self.master = master
        self.thread_queue = queue.Queue()
        #self.new_thread = threading.Thread(target=func, *args, **kwargs)
        self.new_thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        self.new_thread.setDaemon(1)
        self.new_thread.start()
        self.master.after(100, self.listen_for_result)

    def listen_for_result(self):
        try:
            self.res = self.thread_queue.get(0)
        except queue.Empty:
            self.master.after(100, self.listen_for_result)

class DarkLed(Led):

    def __init__(self, root, size):
        super().__init__(root, size)
        bg = ttk.Style().lookup('TFrame', 'background')
        self._canvas['background'] = bg
        self._canvas['bd'] = 2
        self._canvas['relief'] = tk.FLAT
        self._canvas['highlightthickness'] = 0

class LabJackController(u6.U6):

    """Added methods for LabJack U6 control"""

    def __init__(self, numTimers=0, numCounters=0):
        """Initialize just like u6.U6

        Parameters:
        numTimers -- int representing number of timers to initialize (max 4)
        numCounters -- int representing number of counters to initialize (max 2)
        """
        super().__init__()

        self.getCalibrationData()
        # for i in range(20):
        #     self.getFeedback(u6.BitDirWrite(i, 0))  # output
        self.configTimerClock(TimerClockBase=3, TimerClockDivisor=4)
        if numCounters:
            self.configIO(NumberTimersEnabled=numTimers, EnableCounter1=True)
        else:
            self.configIO(NumberTimersEnabled=numTimers)

    def ToggleOn(self, relay):
        """Turns a relay on

        Parameters:
        relay -- str representing the digitial pin on the LabJack
        """
        if relay.startswith('E'):
            IONumber = int(relay[3:]) + 8
        elif relay.startswith('C'):
            IONumber = int(relay[3:]) + 16
        elif relay.startswith('M'):
            IONumber = int(relay[3:]) + 16
        else:
            IONumber = int(relay[3:])
        self.getFeedback(u6.BitDirWrite(int(IONumber), 1))
        self.getFeedback(u6.BitStateWrite(int(IONumber), 0))

    def ToggleOff(self, relay):
        """Turns a relay off

        Parameters:
        relay -- str representing the digitial pin on the LabJack
        """
        if relay.startswith('E'):
            IONumber = int(relay[3:]) + 8
        elif relay.startswith('C'):
            IONumber = int(relay[3:]) + 16
        elif relay.startswith('M'):
            IONumber = int(relay[3:]) + 16
        else:
            IONumber = int(relay[3:])
        self.getFeedback(u6.BitDirWrite(int(IONumber), 0))

    def getRelayState(self, relay):
        """Checks state of relay.

        Parameters:
        relay -- str representing the digitial pin on the LabJack

        Returns -- True if on and False otherwise
        """
        if relay.startswith('E'):
            IONumber = int(relay[3:]) + 8
        elif relay.startswith('C'):
            IONumber = int(relay[3:]) + 16
        elif relay.startswith('M'):
            IONumber = int(relay[3:]) + 16
        else:
            IONumber = int(relay[3:])
        if self.getFeedback(u6.BitDirRead(IONumber)) == [1]:
            return True
        else:
            return False


plt.rc('axes', grid=True)
#plt.style.use('dark_background')
plt.rc('text', color='white')
plt.rc('axes', labelcolor='white')
plt.rc('xtick', color='white')
plt.rc('ytick', color='white')
plt.rc('text', usetex=False)

class Monitor(tk.Tk):

    def __init__(self):
        super().__init__()

        self.starttime = time.time()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.grid_columnconfigure(0, w=1)
        self.grid_rowconfigure(0, w=1)

        self.geometry("300x300")

        s = ttk.Style()
        self.tk.eval('''
         set base_theme_dir themes/awthemes-10.3.0/awthemes-10.3.0/
         package ifneeded awthemes 10.3.0 \
         [list source [file join $base_theme_dir awthemes.tcl]]
         package ifneeded colorutils 4.8\
         [list source [file join $base_theme_dir colorutils.tcl]]
         package ifneeded awdark 7.11\
         [list source [file join $base_theme_dir awdark.tcl]]
         package ifneeded awlight 7.9\
         [list source [file join $base_theme_dir awlight.tcl]]
         package ifneeded awbreezedark 1.0\
         [list source [file join $base_theme_dir awbreezedark.tcl]]
         package ifneeded awblack 7.8\
         [list source [file join $base_theme_dir awblack.tcl]]
         ''')
        self.tk.call('package', 'require', 'awdark')
        self.tk.call('package', 'require', 'awlight')
        s.theme_use('awdark')
        s.configure('.', font=('Times', 16))
        s.configure('TLabelframe.Label', font=('Times', 20, 'bold'))
        s.configure('Small.TLabelframe.Label', font=('Times', 18, 'bold'))
        s.configure('TNotebook.Tab', font=('Times', 18))
        s.configure('Header.TLabel', font=('Times', 18, 'bold underline'))
        s.configure('SubHeader.TLabel', font=('Times', 18, 'underline'))
        s.configure('Red.TButton', foreground='red')

        frame = ttk.Frame(self)
        frame.grid(row=0, column=0, sticky='news')
        frame.grid_columnconfigure(0, w=1)
        frame.grid_rowconfigure(0, w=1)
        self.var = tk.StringVar()
        self.var.set('Gauge Off')
        ttk.Label(frame, textvariable=self.var, anchor='center').grid(row=0, column=0, sticky='news')
        self.Btn = ttk.Button(frame, text='Turn Gauge On', command=self.ToggleGauge)
        self.Btn.grid(row=1, column=0, sticky='ew') 
        self.relay = {'key':'FIO0'}

        try:
            self.LJ = LabJackController(numTimers=1)
        except LabJackException:
            self.LJ = None

        ThreadedTask(self, self.readGauge)

    def on_closing(self):
        plt.close('all')
        root.after(100, root.destroy)

    def ToggleGauge(self):
        if self.LJ.getRelayState(self.relay):
            self.LJ.ToggleOff(self.relay)
            self.Btn['text'] = 'Turn Gauge On'
            self.Btn['style'] = 'TButton'
        else:
            self.LJ.ToggleOn(self.relay)
            self.Btn['text'] = 'Turn Gauge Off'
            self.Btn['style'] = 'Red.TButton'

    def readGauge(self):
        while True:
            V = self.LJ.getAIN(0, resolutionIndex=8)
            if V > 9.8:
                if self.LJ.getRelayState(self.relay):
                    self.var.set('Error')
                else:
                    self.var.set('Gauge Off')
            else:
                self.var.set(f'{10**(V-10):.2e}')
            time.sleep(0.5) 



if __name__ == '__main__':
    root = Monitor()
    root.mainloop()

