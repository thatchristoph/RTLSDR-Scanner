#
# rtlsdr_scan
#
# http://eartoearoak.com/software/rtlsdr-scanner
#
# Copyright 2012 - 2014 Al Brown
#
# A frequency scanning GUI for the OsmoSDR rtl-sdr library at
# http://sdr.osmocom.org/trac/wiki/rtl-sdr
#
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import Queue
import copy
import itertools
import multiprocessing
import os
import platform
import textwrap
from urlparse import urlparse

from PIL import Image
from matplotlib import mlab, patheffects
import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.ticker import ScalarFormatter
import numpy
import rtlsdr
import serial
from wx import grid
import wx
from wx.lib import masked
from wx.lib.agw.cubecolourdialog import CubeColourDialog
from wx.lib.masked.numctrl import NumCtrl

from constants import F_MIN, F_MAX, Cal, SAMPLE_RATE, BANDWIDTH, WINFUNC, \
    TUNER
from controls import TickCellRenderer, SatLevel
from devices import DeviceRTL, DeviceGPS
from events import Event
from file import open_plot, File, export_image
from location import ThreadLocation
from misc import format_precision, format_time, nearest, get_serial_ports, \
    get_version_timestamp, limit
from panels import PanelGraphCompare, PanelColourBar, PanelLine
from plot_line import Plotter
from rtltcp import RtlTcp
from spectrum import count_points, sort_spectrum, Extent
from utils_mpl import get_colours
from utils_wx import close_modeless, ValidatorCoord, load_bitmap


class DialogCompare(wx.Dialog):
    def __init__(self, parent, settings, filename):

        self.settings = settings
        self.dirname = settings.dirScans
        self.filename = filename

        wx.Dialog.__init__(self, parent=parent, title="Compare plots",
                           style=wx.DEFAULT_DIALOG_STYLE |
                           wx.RESIZE_BORDER |
                           wx.MAXIMIZE_BOX)

        self.graph = PanelGraphCompare(self, self.__on_cursor)
        self.graph.show_plot1(settings.compareOne)
        self.graph.show_plot2(settings.compareTwo)
        self.graph.show_plotdiff(settings.compareDiff)

        textPlot1 = wx.StaticText(self, label='Plot 1')
        linePlot1 = PanelLine(self, wx.BLUE)
        self.checkOne = wx.CheckBox(self, wx.ID_ANY)
        self.checkOne.SetValue(settings.compareOne)
        self.buttonPlot1 = wx.Button(self, wx.ID_ANY, 'Load...')
        self.textPlot1 = wx.StaticText(self, label="<None>")
        self.textLoc1 = wx.StaticText(self, label='\n')
        self.Bind(wx.EVT_BUTTON, self.__on_load_plot, self.buttonPlot1)

        textPlot2 = wx.StaticText(self, label='Plot 2')
        linePlot2 = PanelLine(self, wx.GREEN)
        self.checkTwo = wx.CheckBox(self, wx.ID_ANY)
        self.checkTwo.SetValue(settings.compareTwo)
        self.buttonPlot2 = wx.Button(self, wx.ID_ANY, 'Load...')
        self.textPlot2 = wx.StaticText(self, label="<None>")
        self.textLoc2 = wx.StaticText(self, label='\n')
        self.Bind(wx.EVT_BUTTON, self.__on_load_plot, self.buttonPlot2)

        textPlotDiff = wx.StaticText(self, label='Difference')
        linePlotDiff = PanelLine(self, wx.RED)
        self.checkDiff = wx.CheckBox(self, wx.ID_ANY)
        self.checkDiff.SetValue(settings.compareDiff)
        self.textLocDiff = wx.StaticText(self, label='\n')

        font = textPlot1.GetFont()
        fontSize = font.GetPointSize()
        font.SetPointSize(fontSize + 4)
        textPlot1.SetFont(font)
        textPlot2.SetFont(font)
        textPlotDiff.SetFont(font)

        fontStyle = font.GetStyle()
        fontWeight = font.GetWeight()
        font = wx.Font(fontSize, wx.FONTFAMILY_MODERN, fontStyle,
                       fontWeight)
        self.textLoc1.SetFont(font)
        self.textLoc2.SetFont(font)
        self.textLocDiff.SetFont(font)

        buttonClose = wx.Button(self, wx.ID_CLOSE, 'Close')

        self.Bind(wx.EVT_CHECKBOX, self.__on_check1, self.checkOne)
        self.Bind(wx.EVT_CHECKBOX, self.__on_check2, self.checkTwo)
        self.Bind(wx.EVT_CHECKBOX, self.__on_check_diff, self.checkDiff)
        self.Bind(wx.EVT_BUTTON, self.__on_close, buttonClose)

        grid = wx.GridBagSizer(5, 5)

        grid.Add(textPlot1, pos=(0, 0))
        grid.Add(linePlot1, pos=(0, 1), flag=wx.EXPAND)
        grid.Add(self.checkOne, pos=(0, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.buttonPlot1, pos=(1, 0))
        grid.Add(self.textPlot1, pos=(2, 0))
        grid.Add(self.textLoc1, pos=(3, 0))

        grid.Add(wx.StaticLine(self), pos=(5, 0), span=(1, 3), flag=wx.EXPAND)
        grid.Add(textPlot2, pos=(6, 0))
        grid.Add(linePlot2, pos=(6, 1), flag=wx.EXPAND)
        grid.Add(self.checkTwo, pos=(6, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.buttonPlot2, pos=(7, 0))
        grid.Add(self.textPlot2, pos=(8, 0))
        grid.Add(self.textLoc2, pos=(9, 0))

        grid.Add(wx.StaticLine(self), pos=(11, 0), span=(1, 3), flag=wx.EXPAND)
        grid.Add(textPlotDiff, pos=(12, 0))
        grid.Add(linePlotDiff, pos=(12, 1), flag=wx.EXPAND)
        grid.Add(self.checkDiff, pos=(12, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.textLocDiff, pos=(13, 0))

        sizerV = wx.BoxSizer(wx.HORIZONTAL)
        sizerV.Add(self.graph, 1, wx.EXPAND)
        sizerV.Add(grid, 0, wx.ALL, border=5)

        sizerH = wx.BoxSizer(wx.VERTICAL)
        sizerH.Add(sizerV, 1, wx.EXPAND, border=5)
        sizerH.Add(buttonClose, 0, wx.ALL | wx.ALIGN_RIGHT, border=5)

        self.SetSizerAndFit(sizerH)

        close_modeless()

    def __on_cursor(self, locs):
        self.textLoc1.SetLabel(self.__format_loc(locs['x1'], locs['y1']))
        self.textLoc2.SetLabel(self.__format_loc(locs['x2'], locs['y2']))
        self.textLocDiff.SetLabel(self.__format_loc(locs['x3'], locs['y3']))

    def __on_load_plot(self, event):
        dlg = wx.FileDialog(self, "Open a scan", self.dirname, self.filename,
                            File.get_type_filters(File.Types.SAVE),
                            wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.dirname = dlg.GetDirectory()
            self.filename = dlg.GetFilename()
            _scanInfo, spectrum, _location = open_plot(self.dirname,
                                                       self.filename)
            if event.EventObject == self.buttonPlot1:
                self.textPlot1.SetLabel(self.filename)
                self.graph.set_spectrum1(spectrum)
            else:
                self.textPlot2.SetLabel(self.filename)
                self.graph.set_spectrum2(spectrum)

        dlg.Destroy()

    def __on_check1(self, _event):
        checked = self.checkOne.GetValue()
        self.settings.compareOne = checked
        self.graph.show_plot1(checked)

    def __on_check2(self, _event):
        checked = self.checkTwo.GetValue()
        self.settings.compareTwo = checked
        self.graph.show_plot2(checked)

    def __on_check_diff(self, _event):
        checked = self.checkDiff.GetValue()
        self.settings.compareDiff = checked
        self.graph.show_plotdiff(checked)

    def __on_close(self, _event):
        close_modeless()
        self.Destroy()

    def __format_loc(self, x, y):
        if None in [x, y]:
            return ""

        freq, level = format_precision(self.settings, x, y, units=False)

        return '{} MHz\n{}    dB/Hz'.format(freq, level)


class DialogAutoCal(wx.Dialog):
    def __init__(self, parent, freq, callbackCal):
        self.callback = callbackCal
        self.cal = 0

        wx.Dialog.__init__(self, parent=parent, title="Auto Calibration",
                           style=wx.CAPTION)
        self.Bind(wx.EVT_CLOSE, self.__on_close)

        title = wx.StaticText(self, label="Calibrate to a known stable signal")
        font = title.GetFont()
        font.SetPointSize(font.GetPointSize() + 2)
        title.SetFont(font)
        text = wx.StaticText(self, label="Frequency (MHz)")
        self.textFreq = masked.NumCtrl(self, value=freq, fractionWidth=3,
                                       min=F_MIN, max=F_MAX)

        self.buttonCal = wx.Button(self, label="Calibrate")
        if len(parent.devicesRtl) == 0:
            self.buttonCal.Disable()
        self.buttonCal.Bind(wx.EVT_BUTTON, self.__on_cal)
        self.textResult = wx.StaticText(self)

        self.buttonOk = wx.Button(self, wx.ID_OK, 'OK')
        self.buttonOk.Disable()
        self.buttonCancel = wx.Button(self, wx.ID_CANCEL, 'Cancel')

        self.buttonOk.Bind(wx.EVT_BUTTON, self.__on_close)
        self.buttonCancel.Bind(wx.EVT_BUTTON, self.__on_close)

        buttons = wx.StdDialogButtonSizer()
        buttons.AddButton(self.buttonOk)
        buttons.AddButton(self.buttonCancel)
        buttons.Realize()

        sizer = wx.GridBagSizer(10, 10)
        sizer.Add(title, pos=(0, 0), span=(1, 2),
                  flag=wx.ALIGN_CENTRE | wx.ALL, border=10)
        sizer.Add(text, pos=(1, 0), flag=wx.ALL | wx.EXPAND, border=10)
        sizer.Add(self.textFreq, pos=(1, 1), flag=wx.ALL | wx.EXPAND,
                  border=5)
        sizer.Add(self.buttonCal, pos=(2, 0), span=(1, 2),
                  flag=wx.ALIGN_CENTRE | wx.ALL | wx.EXPAND, border=10)
        sizer.Add(self.textResult, pos=(3, 0), span=(1, 2),
                  flag=wx.ALL | wx.EXPAND, border=10)
        sizer.Add(buttons, pos=(4, 0), span=(1, 2),
                  flag=wx.ALL | wx.EXPAND, border=10)

        self.SetSizerAndFit(sizer)

    def __on_cal(self, _event):
        self.buttonCal.Disable()
        self.buttonOk.Disable()
        self.buttonCancel.Disable()
        self.textFreq.Disable()
        self.textResult.SetLabel("Calibrating...")
        self.callback(Cal.START)

    def __on_close(self, event):
        status = [Cal.CANCEL, Cal.OK][event.GetId() == wx.ID_OK]
        self.callback(status)
        self.EndModal(event.GetId())
        return

    def __enable_controls(self):
        self.buttonCal.Enable(True)
        self.buttonOk.Enable(True)
        self.buttonCancel.Enable(True)
        self.textFreq.Enable()

    def set_cal(self, cal):
        self.cal = cal
        self.__enable_controls()
        self.textResult.SetLabel("Correction (ppm): {0:.3f}".format(cal))

    def get_cal(self):
        return self.cal

    def reset_cal(self):
        self.set_cal(self.cal)

    def get_arg1(self):
        return self.textFreq.GetValue()


class DialogImageSize(wx.Dialog):
    def __init__(self, parent, settings, onlyDpi=False):
        wx.Dialog.__init__(self, parent=parent, title='Image settings')

        self.settings = settings

        textWidth = wx.StaticText(self, label="Width (inches)")
        self.ctrlWidth = NumCtrl(self, integerWidth=2, fractionWidth=1)
        self.ctrlWidth.SetValue(settings.exportWidth)
        self.Bind(masked.EVT_NUM, self.__update_size, self.ctrlWidth)

        textHeight = wx.StaticText(self, label="Height (inches)")
        self.ctrlHeight = NumCtrl(self, integerWidth=2, fractionWidth=1)
        self.ctrlHeight.SetValue(settings.exportHeight)
        self.Bind(masked.EVT_NUM, self.__update_size, self.ctrlHeight)

        textDpi = wx.StaticText(self, label="Dots per inch")
        self.spinDpi = wx.SpinCtrl(self)
        self.spinDpi.SetRange(32, 3200)
        self.spinDpi.SetValue(settings.exportDpi)
        self.Bind(wx.EVT_SPINCTRL, self.__update_size, self.spinDpi)

        textSize = wx.StaticText(self, label='Size')
        self.textSize = wx.StaticText(self)
        self.__update_size(None)

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        sizer = wx.GridBagSizer(5, 5)
        sizer.Add(textWidth, pos=(0, 0),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.ctrlWidth, pos=(0, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(textHeight, pos=(1, 0),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.ctrlHeight, pos=(1, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(textDpi, pos=(2, 0),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.spinDpi, pos=(2, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(textSize, pos=(3, 0),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.textSize, pos=(3, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(sizerButtons, pos=(4, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.SetEmptyCellSize((0, 0))

        if onlyDpi:
            textWidth.Hide()
            self.ctrlWidth.Hide()
            textHeight.Hide()
            self.ctrlHeight.Hide()
            self.textSize.Hide()

        self.SetSizerAndFit(sizer)

    def __update_size(self, _event):
        width = self.ctrlWidth.GetValue()
        height = self.ctrlHeight.GetValue()
        dpi = self.spinDpi.GetValue()

        self.textSize.SetLabel('{:.0f}px x {:.0f}px'.format(width * dpi,
                                                            height * dpi))

    def __on_ok(self, _event):
        self.settings.exportWidth = self.ctrlWidth.GetValue()
        self.settings.exportHeight = self.ctrlHeight.GetValue()
        self.settings.exportDpi = self.spinDpi.GetValue()

        self.EndModal(wx.ID_OK)


class DialogSeq(wx.Dialog):
    POLL = 250

    def __init__(self, parent, spectrum, settings):
        self.spectrum = spectrum
        self.settings = settings
        self.sweeps = None
        self.isExporting = False

        wx.Dialog.__init__(self, parent=parent, title='Export Plot Sequence')

        self.queue = Queue.Queue()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.__on_timer, self.timer)
        self.timer.Start(self.POLL)

        self.figure = matplotlib.figure.Figure(facecolor='white')
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.plot = Plotter(self.queue, self.figure, settings)

        self.checkAxes = wx.CheckBox(self, label='Axes')
        self.checkAxes.SetValue(True)
        self.Bind(wx.EVT_CHECKBOX, self.__on_axes, self.checkAxes)
        self.checkGrid = wx.CheckBox(self, label='Grid')
        self.checkGrid.SetValue(True)
        self.Bind(wx.EVT_CHECKBOX, self.__on_grid, self.checkGrid)
        self.checkBar = wx.CheckBox(self, label='Bar')
        self.checkBar.SetValue(True)
        self.Bind(wx.EVT_CHECKBOX, self.__on_bar, self.checkBar)

        sizerCheck = wx.BoxSizer(wx.HORIZONTAL)
        sizerCheck.Add(self.checkAxes, flag=wx.ALL, border=5)
        sizerCheck.Add(self.checkGrid, flag=wx.ALL, border=5)
        sizerCheck.Add(self.checkBar, flag=wx.ALL, border=5)

        self.sweepTimeStamps = sorted([timeStamp for timeStamp in spectrum.keys()])
        sweepChoices = [format_time(timeStamp, True) for timeStamp in self.sweepTimeStamps]

        textStart = wx.StaticText(self, label="Start")
        self.choiceStart = wx.Choice(self, choices=sweepChoices)
        self.choiceStart.SetSelection(0)
        self.Bind(wx.EVT_CHOICE, self.__on_choice, self.choiceStart)

        textEnd = wx.StaticText(self, label="End")
        self.choiceEnd = wx.Choice(self, choices=sweepChoices)
        self.choiceEnd.SetSelection(len(self.sweepTimeStamps) - 1)
        self.Bind(wx.EVT_CHOICE, self.__on_choice, self.choiceEnd)

        self.textSweeps = wx.StaticText(self, label="")

        textSize = wx.StaticText(self, label='Image size')
        self.textSize = wx.StaticText(self)
        buttonSize = wx.Button(self, label='Change...')
        self.Bind(wx.EVT_BUTTON, self.__on_imagesize, buttonSize)
        self.__show_image_size()

        self.editDir = wx.TextCtrl(self)
        self.editDir.SetValue(settings.dirExport)

        textDir = wx.StaticText(self, label='Output directory')
        buttonBrowse = wx.Button(self, label='Browse...')
        self.Bind(wx.EVT_BUTTON, self.__on_browse, buttonBrowse)

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        sizerGrid = wx.GridBagSizer(5, 5)
        sizerGrid.Add(self.canvas, pos=(0, 0), span=(1, 6),
                      flag=wx.EXPAND | wx.ALL, border=5)
        sizerGrid.Add(sizerCheck, pos=(1, 0), span=(1, 6),
                      flag=wx.ALIGN_CENTRE_VERTICAL | wx.ALL, border=5)
        sizerGrid.Add(textStart, pos=(2, 0),
                      flag=wx.ALIGN_CENTRE_VERTICAL | wx.ALL, border=5)
        sizerGrid.Add(self.choiceStart, pos=(2, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(textEnd, pos=(3, 0),
                      flag=wx.ALIGN_CENTRE_VERTICAL | wx.ALL, border=5)
        sizerGrid.Add(self.choiceEnd, pos=(3, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.textSweeps, pos=(3, 2),
                      flag=wx.ALIGN_CENTRE_VERTICAL | wx.ALL, border=5)
        sizerGrid.Add(textSize, pos=(4, 0),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.textSize, pos=(4, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(buttonSize, pos=(4, 2),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(textDir, pos=(5, 0),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.editDir, pos=(5, 1), span=(1, 4),
                      flag=wx.ALL | wx.EXPAND, border=5)
        sizerGrid.Add(buttonBrowse, pos=(5, 5),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(sizerButtons, pos=(6, 5),
                      flag=wx.ALIGN_RIGHT | wx.ALL, border=5)

        self.SetSizerAndFit(sizerGrid)

        self.__draw_plot()

    def __on_choice(self, event):
        start = self.choiceStart.GetSelection()
        end = self.choiceEnd.GetSelection()
        control = event.GetEventObject()

        if start > end:
            if control == self.choiceStart:
                self.choiceStart.SetSelection(end)
            else:
                self.choiceEnd.SetSelection(start)

        self.__draw_plot()

    def __on_axes(self, _event):
        self.plot.set_axes(self.checkAxes.GetValue())
        self.__draw_plot()

    def __on_grid(self, _event):
        self.plot.set_grid(self.checkGrid.GetValue())
        self.__draw_plot()

    def __on_bar(self, _event):
        self.plot.set_bar(self.checkBar.GetValue())
        self.__draw_plot()

    def __on_imagesize(self, _event):
        dlg = DialogImageSize(self, self.settings)
        dlg.ShowModal()
        self.__show_image_size()

    def __on_browse(self, _event):
        directory = self.editDir.GetValue()
        dlg = wx.DirDialog(self, 'Output directory', directory)
        if dlg.ShowModal() == wx.ID_OK:
            directory = dlg.GetPath()
            self.editDir.SetValue(directory)

    def __on_timer(self, _event):
        self.timer.Stop()
        if not self.isExporting:
            while not self.queue.empty():
                event = self.queue.get()
                status = event.data.get_status()

                if status == Event.DRAW:
                    self.canvas.draw()

        self.timer.Start(self.POLL)

    def __on_ok(self, _event):
        self.isExporting = True
        extent = Extent(self.spectrum)
        dlgProgress = wx.ProgressDialog('Exporting', '', len(self.sweeps) - 1,
                                        style=wx.PD_AUTO_HIDE |
                                        wx.PD_CAN_ABORT |
                                        wx.PD_REMAINING_TIME)

        try:
            count = 1
            for timeStamp, sweep in self.sweeps.items():
                name = '{0:.0f}.png'.format(timeStamp)
                directory = self.editDir.GetValue()
                filename = os.path.join(directory, name)

                thread = self.plot.set_plot({timeStamp: sweep}, extent, False)
                thread.join()
                filename = os.path.join(directory, '{0}.png'.format(timeStamp))
                export_image(filename, File.ImageType.PNG,
                             self.figure,
                             self.settings)

                cont, _skip = dlgProgress.Update(count, name)
                if not cont:
                    break
                count += 1
        except IOError as error:
            wx.MessageBox(error.strerror, 'Error', wx.OK | wx.ICON_WARNING)
        finally:
            dlgProgress.Destroy()
            self.EndModal(wx.ID_OK)

    def __spectrum_range(self, start, end):
        sweeps = {}
        for timeStamp, sweep in self.spectrum.items():
            if start <= timeStamp <= end:
                sweeps[timeStamp] = sweep

        self.sweeps = sort_spectrum(sweeps)

    def __draw_plot(self):
        start, end = self.__get_range()
        self.__spectrum_range(start, end)

        self.textSweeps.SetLabel('Sweeps: {}'.format(len(self.sweeps)))

        if len(self.sweeps) > 0:
            total = count_points(self.sweeps)
            if total > 0:
                extent = Extent(self.spectrum)
                self.plot.set_plot(self.sweeps, extent, False)
        else:
            self.plot.clear_plots()

    def __show_image_size(self):
        self.textSize.SetLabel('{0}" x {1}" @ {2}dpi'.format(self.settings.exportWidth,
                                                             self.settings.exportHeight,
                                                             self.settings.exportDpi))

    def __get_range(self):
        start = self.sweepTimeStamps[self.choiceStart.GetSelection()]
        end = self.sweepTimeStamps[self.choiceEnd.GetSelection()]

        return start, end


class DialogGeo(wx.Dialog):
    def __init__(self, parent, spectrum, location, settings):
        self.spectrum = spectrum
        self.location = location
        self.settings = settings
        self.directory = settings.dirExport
        self.colourMap = settings.colourMap
        self.canvas = None
        self.extent = None
        self.xyz = None
        self.plotAxes = False
        self.plotHeat = True
        self.plotCont = True
        self.plotPoint = False
        self.plot = None

        wx.Dialog.__init__(self, parent=parent, title='Export Map')

        self.figure = matplotlib.figure.Figure(facecolor='white')
        self.figure.set_size_inches((6, 6))
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.axes = self.figure.add_subplot(111)

        self.checkAxes = wx.CheckBox(self, label='Axes')
        self.checkAxes.SetValue(self.plotAxes)
        self.Bind(wx.EVT_CHECKBOX, self.__on_axes, self.checkAxes)
        self.checkHeat = wx.CheckBox(self, label='Heat Map')
        self.checkHeat.SetValue(self.plotHeat)
        self.Bind(wx.EVT_CHECKBOX, self.__on_heat, self.checkHeat)
        self.checkCont = wx.CheckBox(self, label='Contour Lines')
        self.checkCont.SetValue(self.plotCont)
        self.Bind(wx.EVT_CHECKBOX, self.__on_cont, self.checkCont)
        self.checkPoint = wx.CheckBox(self, label='Locations')
        self.checkPoint.SetValue(self.plotPoint)
        self.Bind(wx.EVT_CHECKBOX, self.__on_point, self.checkPoint)

        sizerCheck = wx.BoxSizer(wx.HORIZONTAL)
        sizerCheck.Add(self.checkAxes, flag=wx.ALL, border=5)
        sizerCheck.Add(self.checkHeat, flag=wx.ALL, border=5)
        sizerCheck.Add(self.checkCont, flag=wx.ALL, border=5)
        sizerCheck.Add(self.checkPoint, flag=wx.ALL, border=5)

        colours = get_colours()
        self.choiceColour = wx.Choice(self, choices=colours)
        self.choiceColour.SetSelection(colours.index(self.colourMap))
        self.Bind(wx.EVT_CHOICE, self.__on_colour, self.choiceColour)
        self.colourBar = PanelColourBar(self, settings.colourMap)

        freqMin = min(spectrum[min(spectrum)]) * 1000
        freqMax = max(spectrum[min(spectrum)]) * 1000
        bw = freqMax - freqMin

        textCentre = wx.StaticText(self, label='Centre')
        self.spinCentre = wx.SpinCtrl(self)
        self.spinCentre.SetToolTip(wx.ToolTip('Centre frequency (kHz)'))
        self.spinCentre.SetRange(freqMin, freqMax)
        self.spinCentre.SetValue(freqMin + bw / 2)

        textBw = wx.StaticText(self, label='Bandwidth')
        self.spinBw = wx.SpinCtrl(self)
        self.spinBw.SetToolTip(wx.ToolTip('Bandwidth (kHz)'))
        self.spinBw.SetRange(1, bw)
        self.spinBw.SetValue(bw / 10)

        buttonUpdate = wx.Button(self, label='Update')
        self.Bind(wx.EVT_BUTTON, self.__on_update, buttonUpdate)

        textRes = wx.StaticText(self, label='Image resolution')
        self.textRes = wx.StaticText(self)
        buttonRes = wx.Button(self, label='Change...')
        self.Bind(wx.EVT_BUTTON, self.__on_imageres, buttonRes)
        self.__show_image_res()

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        self.__setup_plot()

        sizerGrid = wx.GridBagSizer(5, 5)
        sizerGrid.Add(self.canvas, pos=(0, 0), span=(1, 3),
                      flag=wx.EXPAND | wx.ALL, border=5)
        sizerGrid.Add(self.choiceColour, pos=(1, 0), span=(1, 2),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.colourBar, pos=(1, 2), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(sizerCheck, pos=(2, 0), span=(1, 4),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(textCentre, pos=(3, 0), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.spinCentre, pos=(3, 1), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(textBw, pos=(4, 0), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.spinBw, pos=(4, 1), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(buttonUpdate, pos=(3, 2), span=(2, 1),
                      flag=wx.ALL | wx.ALIGN_CENTRE_VERTICAL, border=5)
        sizerGrid.Add(textRes, pos=(5, 0), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(self.textRes, pos=(5, 1), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(buttonRes, pos=(5, 2), span=(1, 1),
                      flag=wx.ALL, border=5)
        sizerGrid.Add(sizerButtons, pos=(6, 2), span=(1, 1),
                      flag=wx.ALIGN_RIGHT | wx.ALL, border=5)

        self.SetSizerAndFit(sizerGrid)

        self.__draw_plot()

    def __setup_plot(self):
        self.axes.clear()

        if self.plotHeat:
            self.choiceColour.Show()
            self.colourBar.Show()
        else:
            self.choiceColour.Hide()
            self.colourBar.Hide()

        self.axes.set_title('Preview')
        self.axes.set_xlabel('Longitude ($^\circ$)')
        self.axes.set_ylabel('Latitude ($^\circ$)')
        self.axes.set_xlim(auto=True)
        self.axes.set_ylim(auto=True)
        formatter = ScalarFormatter(useOffset=False)
        self.axes.xaxis.set_major_formatter(formatter)
        self.axes.yaxis.set_major_formatter(formatter)

    def __draw_plot(self):
        self.plot = None
        x = []
        y = []
        z = []

        freqCentre = self.spinCentre.GetValue()
        freqBw = self.spinBw.GetValue()
        freqMin = (freqCentre - freqBw) / 1000.
        freqMax = (freqCentre + freqBw) / 1000.

        for timeStamp in self.spectrum:
            spectrum = self.spectrum[timeStamp]
            sweep = [yv for xv, yv in spectrum.items() if freqMin <= xv <= freqMax]
            if len(sweep):
                peak = max(sweep)
                try:
                    location = self.location[timeStamp]
                except KeyError:
                    continue
                x.append(location[1])
                y.append(location[0])
                z.append(peak)

        if len(x) == 0:
            self.__draw_warning()
            return

        xi = numpy.linspace(min(x), max(x), 500)
        yi = numpy.linspace(min(y), max(y), 500)

        try:
            zi = mlab.griddata(x, y, z, xi, yi)
        except:
            self.__draw_warning()
            return

        self.extent = (min(x), max(x), min(y), max(y))
        self.xyz = (x, y, z)

        if self.plotHeat:
            self.plot = self.axes.pcolormesh(xi, yi, zi, cmap=self.colourMap)

        if self.plotCont:
            contours = self.axes.contour(xi, yi, zi, linewidths=0.5,
                                         colors='k')
            self.axes.clabel(contours, inline=1, fontsize='x-small',
                             gid='clabel')

        if self.plotPoint:
            self.axes.plot(x, y, 'wo')
            for posX, posY, posZ in zip(x, y, z):
                self.axes.annotate('{0:.2f}dB'.format(posZ), xy=(posX, posY),
                                   xytext=(-5, 5), ha='right',
                                   textcoords='offset points')

        if matplotlib.__version__ >= '1.3':
            effect = patheffects.withStroke(linewidth=2, foreground="w",
                                            alpha=0.75)
            for child in self.axes.get_children():
                child.set_path_effects([effect])

        if self.plotAxes:
            self.axes.set_axis_on()
        else:
            self.axes.set_axis_off()
        self.canvas.draw()

    def __draw_warning(self):
        self.axes.text(0.5, 0.5, 'Insufficient GPS data',
                       ha='center', va='center',
                       transform=self.axes.transAxes)

    def __on_update(self, _event):
        self.__setup_plot()
        self.__draw_plot()

    def __on_imageres(self, _event):
        dlg = DialogImageSize(self, self.settings, True)
        dlg.ShowModal()
        self.__show_image_res()

    def __on_ok(self, _event):
        self.EndModal(wx.ID_OK)

    def __on_axes(self, _event):
        self.plotAxes = self.checkAxes.GetValue()
        if self.plotAxes:
            self.axes.set_axis_on()
        else:
            self.axes.set_axis_off()
        self.canvas.draw()

    def __on_heat(self, _event):
        self.plotHeat = self.checkHeat.GetValue()
        self.__on_update(None)

    def __on_cont(self, _event):
        self.plotCont = self.checkCont.GetValue()
        self.__on_update(None)

    def __on_point(self, _event):
        self.plotPoint = self.checkPoint.GetValue()
        self.__on_update(None)

    def __on_colour(self, _event):
        self.colourMap = self.choiceColour.GetStringSelection()
        self.colourBar.set_map(self.colourMap)
        if self.plot:
            self.plot.set_cmap(self.colourMap)
            self.canvas.draw()

    def __show_image_res(self):
        self.textRes.SetLabel('{0}dpi'.format(self.settings.exportDpi))

    def get_filename(self):
        return self.filename

    def get_directory(self):
        return self.directory

    def get_extent(self):
        return self.extent

    def get_image(self):
        width = self.extent[1] - self.extent[0]
        height = self.extent[3] - self.extent[2]
        self.figure.set_size_inches((6, 6. * width / height))
        self.figure.set_dpi(self.settings.exportDpi)
        self.axes.set_title('')
        self.figure.patch.set_alpha(0)
        self.axes.axesPatch.set_alpha(0)
        canvas = FigureCanvasAgg(self.figure)
        canvas.draw()

        renderer = canvas.get_renderer()
        if matplotlib.__version__ >= '1.2':
            buf = renderer.buffer_rgba()
        else:
            buf = renderer.buffer_rgba(0, 0)
        size = canvas.get_width_height()
        image = Image.frombuffer('RGBA', size, buf, 'raw', 'RGBA', 0, 1)

        return image

    def get_xyz(self):
        return self.xyz


class DialogOffset(wx.Dialog):
    def __init__(self, parent, device, offset, winFunc):
        self.device = device
        self.offset = offset * 1e3
        self.winFunc = winFunc
        self.band1 = None
        self.band2 = None

        wx.Dialog.__init__(self, parent=parent, title="Scan Offset")

        figure = matplotlib.figure.Figure(facecolor='white')
        self.axes = figure.add_subplot(111)
        self.canvas = FigureCanvas(self, -1, figure)

        textHelp = wx.StaticText(self,
            label="Remove the aerial and press refresh, "
            "adjust the offset so the shaded areas overlay the flattest parts "
            "of the plot_line.")

        textFreq = wx.StaticText(self, label="Test frequency (MHz)")
        self.spinFreq = wx.SpinCtrl(self)
        self.spinFreq.SetRange(F_MIN, F_MAX)
        self.spinFreq.SetValue(200)

        textGain = wx.StaticText(self, label="Test gain (dB)")
        self.spinGain = wx.SpinCtrl(self)
        self.spinGain.SetRange(-100, 200)
        self.spinGain.SetValue(200)

        refresh = wx.Button(self, wx.ID_ANY, 'Refresh')
        self.Bind(wx.EVT_BUTTON, self.__on_refresh, refresh)

        textOffset = wx.StaticText(self, label="Offset (kHz)")
        self.spinOffset = wx.SpinCtrl(self)
        self.spinOffset.SetRange(0, ((SAMPLE_RATE / 2) - BANDWIDTH) / 1e3)
        self.spinOffset.SetValue(offset)
        self.Bind(wx.EVT_SPINCTRL, self.__on_spin, self.spinOffset)

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        boxSizer1 = wx.BoxSizer(wx.HORIZONTAL)
        boxSizer1.Add(textFreq, border=5)
        boxSizer1.Add(self.spinFreq, border=5)
        boxSizer1.Add(textGain, border=5)
        boxSizer1.Add(self.spinGain, border=5)

        boxSizer2 = wx.BoxSizer(wx.HORIZONTAL)
        boxSizer2.Add(textOffset, border=5)
        boxSizer2.Add(self.spinOffset, border=5)

        gridSizer = wx.GridBagSizer(5, 5)
        gridSizer.Add(self.canvas, pos=(0, 0), span=(1, 2),
                      flag=wx.ALIGN_CENTRE | wx.ALL, border=5)
        gridSizer.Add(textHelp, pos=(1, 0), span=(1, 2),
                      flag=wx.ALIGN_CENTRE | wx.ALL, border=5)
        gridSizer.Add(boxSizer1, pos=(2, 0), span=(1, 2),
                      flag=wx.ALIGN_CENTRE | wx.ALL, border=5)
        gridSizer.Add(refresh, pos=(3, 0), span=(1, 2),
                      flag=wx.ALIGN_CENTRE | wx.ALL, border=5)
        gridSizer.Add(boxSizer2, pos=(4, 0), span=(1, 2),
                      flag=wx.ALIGN_CENTRE | wx.ALL, border=5)
        gridSizer.Add(sizerButtons, pos=(5, 1), span=(1, 1),
                      flag=wx.ALIGN_RIGHT | wx.ALL, border=5)

        self.SetSizerAndFit(gridSizer)
        self.__draw_limits()

        self.__setup_plot()

    def __setup_plot(self):
        self.axes.clear()
        self.band1 = None
        self.band2 = None
        self.axes.set_xlabel("Frequency (MHz)")
        self.axes.set_ylabel('Level ($\mathsf{dB/\sqrt{Hz}}$)')
        self.axes.set_yscale('log')
        self.axes.set_xlim(-1, 1)
        self.axes.set_ylim(auto=True)
        self.axes.grid(True)
        self.__draw_limits()

    def __plot(self, capture):
        self.__setup_plot()
        pos = WINFUNC[::2].index(self.winFunc)
        function = WINFUNC[1::2][pos]
        powers, freqs = matplotlib.mlab.psd(capture,
                                            NFFT=1024,
                                            Fs=SAMPLE_RATE / 1e6,
                                            window=function(1024))

        plot = []
        for x, y in itertools.izip(freqs, powers):
            plot.append((x, y))
        plot.sort()
        x, y = numpy.transpose(plot)
        self.axes.plot(x, y, linewidth=0.4)
        self.canvas.draw()

    def __on_ok(self, _event):
        self.EndModal(wx.ID_OK)

    def __on_refresh(self, _event):
        dlg = wx.BusyInfo('Please wait...')

        try:
            if self.device.isDevice:
                sdr = rtlsdr.RtlSdr(self.device.indexRtl)
            else:
                sdr = RtlTcp(self.device.server, self.device.port)
            sdr.set_sample_rate(SAMPLE_RATE)
            sdr.set_center_freq(self.spinFreq.GetValue() * 1e6)
            sdr.set_gain(self.spinGain.GetValue())
            capture = sdr.read_samples(2 ** 21)
            sdr.close()
        except IOError as error:
            if self.device.isDevice:
                message = error.message
            else:
                message = error
            dlg.Destroy()
            dlg = wx.MessageDialog(self,
                                   'Capture failed:\n{0}'.format(message),
                                   'Error',
                                   wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return

        self.__plot(capture)

        dlg.Destroy()

    def __on_spin(self, _event):
        self.offset = self.spinOffset.GetValue() * 1e3
        self.__draw_limits()

    def __draw_limits(self):
        limit1 = self.offset
        limit2 = limit1 + BANDWIDTH / 2
        limit1 /= 1e6
        limit2 /= 1e6
        if self.band1 is not None:
            self.band1.remove()
        if self.band2 is not None:
            self.band2.remove()
        self.band1 = self.axes.axvspan(limit1, limit2, color='g', alpha=0.25)
        self.band2 = self.axes.axvspan(-limit1, -limit2, color='g', alpha=0.25)
        self.canvas.draw()

    def get_offset(self):
        return self.offset / 1e3


class DialogProperties(wx.Dialog):
    def __init__(self, parent, scanInfo):
        wx.Dialog.__init__(self, parent, title="Scan Properties")

        self.scanInfo = scanInfo

        box = wx.BoxSizer(wx.VERTICAL)

        grid = wx.GridBagSizer(0, 0)

        boxScan = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Scan"),
                                    wx.HORIZONTAL)

        gridScan = wx.GridBagSizer(0, 0)

        textDesc = wx.StaticText(self, label="Description")
        gridScan.Add(textDesc, (0, 0), (1, 1), wx.ALL, 5)
        self.textCtrlDesc = wx.TextCtrl(self, value=scanInfo.desc,
                                        style=wx.TE_MULTILINE)
        gridScan.Add(self.textCtrlDesc, (0, 1), (2, 2), wx.ALL | wx.EXPAND, 5)

        textStart = wx.StaticText(self, label="Start")
        gridScan.Add(textStart, (2, 0), (1, 1), wx.ALL, 5)
        textCtrlStart = wx.TextCtrl(self, value="Unknown",
                                    style=wx.TE_READONLY)
        if scanInfo.start is not None:
            textCtrlStart.SetValue(str(scanInfo.start))
        gridScan.Add(textCtrlStart, (2, 1), (1, 1), wx.ALL, 5)
        textMHz1 = wx.StaticText(self, wx.ID_ANY, label="MHz")
        gridScan.Add(textMHz1, (2, 2), (1, 1), wx.ALL, 5)

        textStop = wx.StaticText(self, label="Stop")
        gridScan.Add(textStop, (3, 0), (1, 1), wx.ALL, 5)
        textCtrlStop = wx.TextCtrl(self, value="Unknown",
                                   style=wx.TE_READONLY)
        if scanInfo.stop is not None:
            textCtrlStop.SetValue(str(scanInfo.stop))
        gridScan.Add(textCtrlStop, (3, 1), (1, 1), wx.ALL, 5)
        textMHz2 = wx.StaticText(self, label="MHz")
        gridScan.Add(textMHz2, (3, 2), (1, 1), wx.ALL, 5)

        textDwell = wx.StaticText(self, label="Dwell")
        gridScan.Add(textDwell, (4, 0), (1, 1), wx.ALL, 5)
        textCtrlDwell = wx.TextCtrl(self, value="Unknown",
                                    style=wx.TE_READONLY)
        if scanInfo.dwell is not None:
            textCtrlDwell.SetValue(str(scanInfo.dwell))
        gridScan.Add(textCtrlDwell, (4, 1), (1, 1), wx.ALL, 5)
        textSeconds = wx.StaticText(self, label="seconds")
        gridScan.Add(textSeconds, (4, 2), (1, 1), wx.ALL, 5)

        textNfft = wx.StaticText(self, label="FFT Size")
        gridScan.Add(textNfft, (5, 0), (1, 1), wx.ALL, 5)
        textCtrlNfft = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.nfft is not None:
            textCtrlNfft.SetValue(str(scanInfo.nfft))
        gridScan.Add(textCtrlNfft, (5, 1), (1, 1), wx.ALL, 5)

        textRbw = wx.StaticText(self, label="RBW")
        gridScan.Add(textRbw, (6, 0), (1, 1), wx.ALL, 5)
        rbw = ((SAMPLE_RATE / scanInfo.nfft) / 1000.0) * 2.0
        textCtrlStop = wx.TextCtrl(self, value="{0:.3f}".format(rbw),
                                   style=wx.TE_READONLY)
        gridScan.Add(textCtrlStop, (6, 1), (1, 1), wx.ALL, 5)
        textKHz = wx.StaticText(self, label="kHz")
        gridScan.Add(textKHz, (6, 2), (1, 1), wx.ALL, 5)

        textTime = wx.StaticText(self, label="First scan")
        gridScan.Add(textTime, (7, 0), (1, 1), wx.ALL, 5)
        textCtrlTime = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.timeFirst is not None:
            textCtrlTime.SetValue(format_time(scanInfo.timeFirst, True))
        gridScan.Add(textCtrlTime, (7, 1), (1, 1), wx.ALL, 5)

        textTime = wx.StaticText(self, label="Last scan")
        gridScan.Add(textTime, (8, 0), (1, 1), wx.ALL, 5)
        textCtrlTime = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.timeLast is not None:
            textCtrlTime.SetValue(format_time(scanInfo.timeLast, True))
        gridScan.Add(textCtrlTime, (8, 1), (1, 1), wx.ALL, 5)

        textLat = wx.StaticText(self, label="Latitude")
        gridScan.Add(textLat, (9, 0), (1, 1), wx.ALL, 5)
        self.textCtrlLat = wx.TextCtrl(self, value="Unknown")
        self.textCtrlLat.SetValidator(ValidatorCoord(True))
        if scanInfo.lat is not None:
            self.textCtrlLat.SetValue(str(scanInfo.lat))
        gridScan.Add(self.textCtrlLat, (9, 1), (1, 1), wx.ALL, 5)

        textLon = wx.StaticText(self, label="Longitude")
        gridScan.Add(textLon, (10, 0), (1, 1), wx.ALL, 5)
        self.textCtrlLon = wx.TextCtrl(self, value="Unknown")
        self.textCtrlLon.SetValidator(ValidatorCoord(False))
        if scanInfo.lon is not None:
            self.textCtrlLon.SetValue(str(scanInfo.lon))
        gridScan.Add(self.textCtrlLon, (10, 1), (1, 1), wx.ALL, 5)

        boxScan.Add(gridScan, 0, 0, 5)

        grid.Add(boxScan, (0, 0), (1, 1), wx.ALL | wx.EXPAND, 5)

        boxDevice = wx.StaticBoxSizer(wx.StaticBox(self, label="Device"),
                                      wx.VERTICAL)

        gridDevice = wx.GridBagSizer(0, 0)

        textName = wx.StaticText(self, label="Name")
        gridDevice.Add(textName, (0, 0), (1, 1), wx.ALL, 5)
        textCtrlName = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.name is not None:
            textCtrlName.SetValue(scanInfo.name)
        gridDevice.Add(textCtrlName, (0, 1), (1, 2), wx.ALL | wx.EXPAND, 5)

        textTuner = wx.StaticText(self, label="Tuner")
        gridDevice.Add(textTuner, (1, 0), (1, 1), wx.ALL, 5)
        textCtrlTuner = wx.TextCtrl(self, value="Unknown",
                                    style=wx.TE_READONLY)
        if scanInfo.tuner != -1:
            textCtrlTuner.SetValue(TUNER[scanInfo.tuner])
        gridDevice.Add(textCtrlTuner, (1, 1), (1, 2), wx.ALL | wx.EXPAND, 5)

        testGain = wx.StaticText(self, label="Gain")
        gridDevice.Add(testGain, (2, 0), (1, 1), wx.ALL, 5)
        textCtrlGain = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.gain is not None:
            textCtrlGain.SetValue(str(scanInfo.gain))
        gridDevice.Add(textCtrlGain, (2, 1), (1, 1), wx.ALL, 5)
        textDb = wx.StaticText(self, label="dB")
        gridDevice.Add(textDb, (2, 2), (1, 1), wx.ALL, 5)

        textLo = wx.StaticText(self, label="LO")
        gridDevice.Add(textLo, (3, 0), (1, 1), wx.ALL, 5)
        textCtrlLo = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.lo is not None:
            textCtrlLo.SetValue(str(scanInfo.lo))
        gridDevice.Add(textCtrlLo, (3, 1), (1, 1), wx.ALL, 5)
        textMHz3 = wx.StaticText(self, label="MHz")
        gridDevice.Add(textMHz3, (3, 2), (1, 1), wx.ALL, 5)

        textCal = wx.StaticText(self, label="Calibration")
        gridDevice.Add(textCal, (4, 0), (1, 1), wx.ALL, 5)
        textCtrlCal = wx.TextCtrl(self, value="Unknown", style=wx.TE_READONLY)
        if scanInfo.calibration is not None:
            textCtrlCal.SetValue(str(scanInfo.calibration))
        gridDevice.Add(textCtrlCal, (4, 1), (1, 1), wx.ALL, 5)
        testPpm = wx.StaticText(self, label="ppm")
        gridDevice.Add(testPpm, (4, 2), (1, 1), wx.ALL, 5)

        boxDevice.Add(gridDevice, 1, wx.EXPAND, 5)

        grid.Add(boxDevice, (1, 0), (1, 1), wx.ALL | wx.EXPAND, 5)

        box.Add(grid, 1, wx.ALL | wx.EXPAND, 5)

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)
        box.Add(sizerButtons, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizerAndFit(box)

    def __on_ok(self, _event):
        self.scanInfo.desc = self.textCtrlDesc.GetValue()
        if self.Validate():
            lat = self.textCtrlLat.GetValue()
            if len(lat) == 0 or lat == "-" or lat.lower() == "unknown":
                self.scanInfo.lat = None
            else:
                self.scanInfo.lat = float(lat)

            lon = self.textCtrlLon.GetValue()
            if len(lon) == 0 or lon == "-" or lon.lower() == "unknown":
                self.scanInfo.lon = None
            else:
                self.scanInfo.lon = float(lon)

            self.EndModal(wx.ID_CLOSE)


class DialogPrefs(wx.Dialog):
    def __init__(self, parent, settings):
        self.settings = settings
        self.index = 0

        wx.Dialog.__init__(self, parent=parent, title="Preferences")

        self.colours = get_colours()
        self.winFunc = settings.winFunc
        self.background = settings.background

        self.checkSaved = wx.CheckBox(self, wx.ID_ANY,
                                      "Save warning")
        self.checkSaved.SetValue(settings.saveWarn)
        self.checkSaved.SetToolTip(wx.ToolTip('Prompt to save scan on exit'))
        self.checkAlert = wx.CheckBox(self, wx.ID_ANY,
                                      "Level alert (dB)")
        self.checkAlert.SetValue(settings.alert)
        self.checkAlert.SetToolTip(wx.ToolTip('Play alert when level exceeded'))
        self.Bind(wx.EVT_CHECKBOX, self.__on_alert, self.checkAlert)
        self.spinLevel = wx.SpinCtrl(self, wx.ID_ANY, min=-100, max=20)
        self.spinLevel.SetValue(settings.alertLevel)
        self.spinLevel.Enable(settings.alert)
        self.spinLevel.SetToolTip(wx.ToolTip('Alert threshold'))
        textBackground = wx.StaticText(self, label='Background colour')
        self.buttonBackground = wx.Button(self, wx.ID_ANY)
        self.buttonBackground.SetBackgroundColour(self.background)
        self.Bind(wx.EVT_BUTTON, self.__on_background, self.buttonBackground)
        textColour = wx.StaticText(self, label="Colour map")
        self.choiceColour = wx.Choice(self, choices=self.colours)
        self.choiceColour.SetSelection(self.colours.index(settings.colourMap))
        self.Bind(wx.EVT_CHOICE, self.__on_choice, self.choiceColour)
        self.colourBar = PanelColourBar(self, settings.colourMap)
        self.checkPoints = wx.CheckBox(self, wx.ID_ANY,
                                       "Limit points")
        self.checkPoints.SetValue(settings.pointsLimit)
        self.checkPoints.SetToolTip(wx.ToolTip('Limit the resolution of plots'))
        self.Bind(wx.EVT_CHECKBOX, self.__on_points, self.checkPoints)
        self.spinPoints = wx.SpinCtrl(self, wx.ID_ANY, min=1000, max=100000)
        self.spinPoints.Enable(settings.pointsLimit)
        self.spinPoints.SetValue(settings.pointsMax)
        self.spinPoints.SetToolTip(wx.ToolTip('Maximum number of points to plot_line'))
        textDpi = wx.StaticText(self, label='Export DPI')
        self.spinDpi = wx.SpinCtrl(self, wx.ID_ANY, min=72, max=6000)
        self.spinDpi.SetValue(settings.exportDpi)
        self.spinDpi.SetToolTip(wx.ToolTip('DPI of exported images'))
        self.checkTune = wx.CheckBox(self, wx.ID_ANY,
                                     "Tune SDR#")
        self.checkTune.SetValue(settings.clickTune)
        self.checkTune.SetToolTip(wx.ToolTip('Double click plot_line to tune SDR#'))
        textPlugin = wx.HyperlinkCtrl(self, wx.ID_ANY,
                                      label="(Requires plugin)",
                                      url="http://eartoearoak.com/software/sdrsharp-net-remote")

        self.radioAvg = wx.RadioButton(self, wx.ID_ANY, 'Average Scans',
                                       style=wx.RB_GROUP)
        self.radioAvg.SetToolTip(wx.ToolTip('Average level with each scan'))
        self.Bind(wx.EVT_RADIOBUTTON, self.__on_radio, self.radioAvg)
        self.radioRetain = wx.RadioButton(self, wx.ID_ANY,
                                          'Retain previous scans')
        self.radioRetain.SetToolTip(wx.ToolTip('Can be slow'))
        self.Bind(wx.EVT_RADIOBUTTON, self.__on_radio, self.radioRetain)
        self.radioRetain.SetValue(settings.retainScans)

        textMaxScans = wx.StaticText(self, label="Max scans")
        self.spinCtrlMaxScans = wx.SpinCtrl(self)
        self.spinCtrlMaxScans.SetRange(1, 500)
        self.spinCtrlMaxScans.SetValue(settings.retainMax)
        self.spinCtrlMaxScans.SetToolTip(wx.ToolTip('Maximum previous scans'
                                                    ' to display'))

        self.checkFade = wx.CheckBox(self, wx.ID_ANY,
                                     "Fade previous scans")
        self.checkFade.SetValue(settings.fadeScans)
        textWidth = wx.StaticText(self, label="Line width")
        self.ctrlWidth = NumCtrl(self, integerWidth=2, fractionWidth=1)
        self.ctrlWidth.SetValue(settings.lineWidth)

        self.__on_radio(None)

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        gengrid = wx.GridBagSizer(10, 10)
        gengrid.Add(self.checkSaved, pos=(0, 0))
        gengrid.Add(self.checkAlert, pos=(1, 0), flag=wx.ALIGN_CENTRE)
        gengrid.Add(self.spinLevel, pos=(1, 1))
        gengrid.Add(textBackground, pos=(2, 0), flag=wx.ALIGN_CENTRE)
        gengrid.Add(self.buttonBackground, pos=(2, 1))
        gengrid.Add(textColour, pos=(3, 0))
        gengrid.Add(self.choiceColour, pos=(3, 1))
        gengrid.Add(self.colourBar, pos=(3, 2))
        gengrid.Add(self.checkPoints, pos=(4, 0))
        gengrid.Add(self.spinPoints, pos=(4, 1))
        gengrid.Add(textDpi, pos=(5, 0))
        gengrid.Add(self.spinDpi, pos=(5, 1))
        gengrid.Add(self.checkTune, pos=(6, 0))
        gengrid.Add(textPlugin, pos=(6, 1))
        genbox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "General"))
        genbox.Add(gengrid, 0, wx.ALL | wx.ALIGN_CENTRE_VERTICAL, 10)

        congrid = wx.GridBagSizer(10, 10)
        congrid.Add(self.radioAvg, pos=(0, 0))
        congrid.Add(self.radioRetain, pos=(1, 0))
        congrid.Add(textMaxScans, pos=(2, 0),
                    flag=wx.ALIGN_CENTRE_VERTICAL)
        congrid.Add(self.spinCtrlMaxScans, pos=(2, 1))
        conbox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY,
                                                "Continuous Scans"),
                                   wx.VERTICAL)
        conbox.Add(congrid, 0, wx.ALL | wx.EXPAND, 10)

        plotgrid = wx.GridBagSizer(10, 10)
        plotgrid.Add(self.checkFade, pos=(0, 0))
        plotgrid.Add(textWidth, pos=(1, 0))
        plotgrid.Add(self.ctrlWidth, pos=(1, 1))
        plotbox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Plot View"),
                                    wx.HORIZONTAL)
        plotbox.Add(plotgrid, 0, wx.ALL | wx.EXPAND, 10)

        grid = wx.GridBagSizer(10, 10)
        grid.Add(genbox, pos=(0, 0), span=(1, 2), flag=wx.EXPAND)
        grid.Add(conbox, pos=(1, 0), span=(1, 2), flag=wx.EXPAND)
        grid.Add(plotbox, pos=(2, 0), span=(1, 2), flag=wx.EXPAND)
        grid.Add(sizerButtons, pos=(3, 1), flag=wx.EXPAND)

        box = wx.BoxSizer()
        box.Add(grid, flag=wx.ALL | wx.ALIGN_CENTRE, border=10)

        self.SetSizerAndFit(box)

    def __on_alert(self, _event):
        enabled = self.checkAlert.GetValue()
        self.spinLevel.Enable(enabled)

    def __on_points(self, _event):
        enabled = self.checkPoints.GetValue()
        self.spinPoints.Enable(enabled)

    def __on_background(self, _event):
        colour = wx.ColourData()
        colour.SetColour(self.background)

        dlg = CubeColourDialog(self, colour, 0)
        if dlg.ShowModal() == wx.ID_OK:
            newColour = dlg.GetColourData().GetColour()
            self.background = newColour.GetAsString(wx.C2S_HTML_SYNTAX)
            self.buttonBackground.SetBackgroundColour(self.background)
        dlg.Destroy()

    def __on_radio(self, _event):
        enabled = self.radioRetain.GetValue()
        self.checkFade.Enable(enabled)
        self.spinCtrlMaxScans.Enable(enabled)

    def __on_choice(self, _event):
        self.colourBar.set_map(self.choiceColour.GetStringSelection())
        self.choiceColour.SetFocus()

    def __on_ok(self, _event):
        self.settings.saveWarn = self.checkSaved.GetValue()
        self.settings.alert = self.checkAlert.GetValue()
        self.settings.alertLevel = self.spinLevel.GetValue()
        self.settings.clickTune = self.checkTune.GetValue()
        self.settings.pointsLimit = self.checkPoints.GetValue()
        self.settings.pointsMax = self.spinPoints.GetValue()
        self.settings.exportDpi = self.spinDpi.GetValue()
        self.settings.retainScans = self.radioRetain.GetValue()
        self.settings.fadeScans = self.checkFade.GetValue()
        self.settings.lineWidth = self.ctrlWidth.GetValue()
        self.settings.retainMax = self.spinCtrlMaxScans.GetValue()
        self.settings.colourMap = self.choiceColour.GetStringSelection()
        self.settings.background = self.background

        self.EndModal(wx.ID_OK)


class DialogAdvPrefs(wx.Dialog):
    def __init__(self, parent, settings):
        self.settings = settings

        wx.Dialog.__init__(self, parent=parent, title="Advanced Preferences")

        self.winFunc = settings.winFunc

        textOverlap = wx.StaticText(self, label='PSD Overlap (%)')
        self.slideOverlap = wx.Slider(self, wx.ID_ANY,
                                      settings.overlap * 100,
                                      0, 75,
                                      style=wx.SL_LABELS)
        self.slideOverlap.SetToolTip(wx.ToolTip('Power spectral density'
                                                ' overlap'))
        textWindow = wx.StaticText(self, label='Window')
        self.buttonWindow = wx.Button(self, wx.ID_ANY, self.winFunc)
        self.Bind(wx.EVT_BUTTON, self.__on_window, self.buttonWindow)

        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons = wx.StdDialogButtonSizer()
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        advgrid = wx.GridBagSizer(10, 10)
        advgrid.Add(textOverlap, pos=(0, 0),
                    flag=wx.ALL | wx.ALIGN_CENTRE)
        advgrid.Add(self.slideOverlap, pos=(0, 1), flag=wx.EXPAND)
        advgrid.Add(textWindow, pos=(1, 0), flag=wx.EXPAND)
        advgrid.Add(self.buttonWindow, pos=(1, 1))
        advgrid.Add(sizerButtons, pos=(2, 1), flag=wx.EXPAND)

        advBox = wx.BoxSizer()
        advBox.Add(advgrid, flag=wx.ALL | wx.ALIGN_CENTRE, border=10)

        self.SetSizerAndFit(advBox)

    def __on_window(self, _event):
        dlg = DialogWinFunc(self, self.winFunc)
        if dlg.ShowModal() == wx.ID_OK:
            self.winFunc = dlg.get_win_func()
            self.buttonWindow.SetLabel(self.winFunc)
        dlg.Destroy()

    def __on_ok(self, _event):
        self.settings.overlap = self.slideOverlap.GetValue() / 100.0
        self.settings.winFunc = self.winFunc

        self.EndModal(wx.ID_OK)


class DialogFormatting(wx.Dialog):
    def __init__(self, parent, settings):
        self.settings = settings

        wx.Dialog.__init__(self, parent=parent, title="Number formatting")

        textFreq = wx.StaticText(self, label='Frequency precision')
        self.spinFreq = wx.SpinCtrl(self, wx.ID_ANY, min=0, max=6)
        self.spinFreq.SetValue(settings.precisionFreq)
        self.spinFreq.SetToolTip(wx.ToolTip('Displayed frequency decimal precision'))

        textLevel = wx.StaticText(self, label='Level precision')
        self.spinLevel = wx.SpinCtrl(self, wx.ID_ANY, min=0, max=2)
        self.spinLevel.SetValue(settings.precisionLevel)
        self.spinLevel.SetToolTip(wx.ToolTip('Displayed level decimal precision'))

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        sizer = wx.GridBagSizer(5, 5)
        sizer.Add(textFreq, pos=(0, 0),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.spinFreq, pos=(0, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(textLevel, pos=(1, 0),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.spinLevel, pos=(1, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(sizerButtons, pos=(2, 1),
                  flag=wx.EXPAND | wx.ALL, border=5)

        self.SetSizerAndFit(sizer)

    def __on_ok(self, _event):
        self.settings.precisionFreq = self.spinFreq.GetValue()
        self.settings.precisionLevel = self.spinLevel.GetValue()

        self.EndModal(wx.ID_OK)


class DialogWinFunc(wx.Dialog):
    def __init__(self, parent, winFunc):
        self.winFunc = winFunc
        x = numpy.linspace(-numpy.pi, numpy.pi, 1000)
        self.data = numpy.sin(x) + 0j

        wx.Dialog.__init__(self, parent=parent, title="Window Function")

        self.figure = matplotlib.figure.Figure(facecolor='white',
                                               figsize=(5, 4))
        self.figure.suptitle('Window Function')
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.axesWin = self.figure.add_subplot(211)
        self.axesFft = self.figure.add_subplot(212)

        text = wx.StaticText(self, label='Function')

        self.choice = wx.Choice(self, choices=WINFUNC[::2])
        self.choice.SetSelection(WINFUNC[::2].index(winFunc))

        sizerButtons = wx.StdDialogButtonSizer()
        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        sizerFunction = wx.BoxSizer(wx.HORIZONTAL)
        sizerFunction.Add(text, flag=wx.ALL, border=5)
        sizerFunction.Add(self.choice, flag=wx.ALL, border=5)

        sizerGrid = wx.GridBagSizer(5, 5)
        sizerGrid.Add(self.canvas, pos=(0, 0), span=(1, 2), border=5)
        sizerGrid.Add(sizerFunction, pos=(1, 0), span=(1, 2),
                      flag=wx.ALIGN_CENTRE | wx.ALL, border=5)
        sizerGrid.Add(sizerButtons, pos=(2, 1),
                      flag=wx.ALIGN_RIGHT | wx.ALL, border=5)

        self.Bind(wx.EVT_CHOICE, self.__on_choice, self.choice)
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        self.__plot()

        self.SetSizerAndFit(sizerGrid)

    def __plot(self):
        pos = WINFUNC[::2].index(self.winFunc)
        function = WINFUNC[1::2][pos](512)

        self.axesWin.clear()
        self.axesWin.plot(function, 'g')
        self.axesWin.set_xlabel('Time')
        self.axesWin.set_ylabel('Multiplier')
        self.axesWin.set_xlim(0, 512)
        self.axesWin.set_xticklabels([])
        self.axesFft.clear()
        self.axesFft.psd(self.data, NFFT=512, Fs=1000, window=function)
        self.axesFft.set_xlabel('Frequency')
        self.axesFft.set_ylabel('$\mathsf{dB/\sqrt{Hz}}$')
        self.axesFft.set_xlim(-256, 256)
        self.axesFft.set_xticklabels([])
        self.figure.tight_layout()

        self.canvas.draw()

    def __on_choice(self, _event):
        self.winFunc = WINFUNC[::2][self.choice.GetSelection()]
        self.plot()

    def __on_ok(self, _event):
        self.EndModal(wx.ID_OK)

    def get_win_func(self):
        return self.winFunc


class DialogDevicesRTL(wx.Dialog):
    COL_SEL, COL_DEV, COL_TUN, COL_SER, COL_IND, \
        COL_GAIN, COL_CAL, COL_LO, COL_OFF = range(9)

    def __init__(self, parent, devices, settings):
        self.devices = copy.copy(devices)
        self.settings = settings
        self.index = None

        wx.Dialog.__init__(self, parent=parent, title="Radio Devices")

        self.gridDev = grid.Grid(self)
        self.gridDev.CreateGrid(len(self.devices), 9)
        self.gridDev.SetRowLabelSize(0)
        self.gridDev.SetColLabelValue(self.COL_SEL, "Selected")
        self.gridDev.SetColLabelValue(self.COL_DEV, "Device")
        self.gridDev.SetColLabelValue(self.COL_TUN, "Tuner")
        self.gridDev.SetColLabelValue(self.COL_SER, "Serial Number")
        self.gridDev.SetColLabelValue(self.COL_IND, "Index")
        self.gridDev.SetColLabelValue(self.COL_GAIN, "Gain\n(dB)")
        self.gridDev.SetColLabelValue(self.COL_CAL, "Calibration\n(ppm)")
        self.gridDev.SetColLabelValue(self.COL_LO, "LO\n(MHz)")
        self.gridDev.SetColLabelValue(self.COL_OFF, "Band Offset\n(kHz)")
        self.gridDev.SetColFormatFloat(self.COL_GAIN, -1, 1)
        self.gridDev.SetColFormatFloat(self.COL_CAL, -1, 3)
        self.gridDev.SetColFormatFloat(self.COL_LO, -1, 3)
        self.gridDev.SetColFormatFloat(self.COL_OFF, -1, 0)

        self.__set_dev_grid()
        self.Bind(grid.EVT_GRID_CELL_LEFT_CLICK, self.__on_click)

        serverSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonAdd = wx.Button(self, wx.ID_ADD)
        self.buttonDel = wx.Button(self, wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self.__on_add, buttonAdd)
        self.Bind(wx.EVT_BUTTON, self.__on_del, self.buttonDel)
        serverSizer.Add(buttonAdd, 0, wx.ALL)
        serverSizer.Add(self.buttonDel, 0, wx.ALL)
        self.__set_button_state()

        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons = wx.StdDialogButtonSizer()
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        self.devbox = wx.BoxSizer(wx.VERTICAL)
        self.devbox.Add(self.gridDev, 1, wx.ALL | wx.EXPAND, 10)
        self.devbox.Add(serverSizer, 0, wx.ALL | wx.EXPAND, 10)
        self.devbox.Add(sizerButtons, 0, wx.ALL | wx.EXPAND, 10)

        self.SetSizerAndFit(self.devbox)

    def __set_dev_grid(self):
        colourBackground = self.gridDev.GetLabelBackgroundColour()
        attributes = grid.GridCellAttr()
        attributes.SetBackgroundColour(colourBackground)
        self.gridDev.SetColAttr(self.COL_IND, attributes)

        self.gridDev.ClearGrid()

        i = 0
        for device in self.devices:
            self.gridDev.SetReadOnly(i, self.COL_SEL, True)
            self.gridDev.SetReadOnly(i, self.COL_DEV, device.isDevice)
            self.gridDev.SetReadOnly(i, self.COL_TUN, True)
            self.gridDev.SetReadOnly(i, self.COL_SER, True)
            self.gridDev.SetReadOnly(i, self.COL_IND, True)
            self.gridDev.SetCellRenderer(i, self.COL_SEL,
                                         TickCellRenderer())
            if device.isDevice:
                cell = grid.GridCellChoiceEditor(map(str, device.gains),
                                                 allowOthers=False)
                self.gridDev.SetCellEditor(i, self.COL_GAIN, cell)
            self.gridDev.SetCellEditor(i, self.COL_CAL,
                                       grid.GridCellFloatEditor(-1, 3))
            self.gridDev.SetCellEditor(i, self.COL_LO,
                                       grid.GridCellFloatEditor(-1, 3))
            if device.isDevice:
                self.gridDev.SetCellValue(i, self.COL_DEV, device.name)
                self.gridDev.SetCellValue(i, self.COL_SER, str(device.serial))
                self.gridDev.SetCellValue(i, self.COL_IND, str(i))
                self.gridDev.SetCellBackgroundColour(i, self.COL_DEV,
                                                     colourBackground)
                self.gridDev.SetCellValue(i, self.COL_GAIN,
                                          str(nearest(device.gain,
                                                      device.gains)))
            else:
                self.gridDev.SetCellValue(i, self.COL_DEV,
                                          '{0}:{1}'.format(device.server,
                                                           device.port))
                self.gridDev.SetCellValue(i, self.COL_SER, '')
                self.gridDev.SetCellValue(i, self.COL_IND, '')
                self.gridDev.SetCellValue(i, self.COL_GAIN, str(device.gain))
            self.gridDev.SetCellBackgroundColour(i, self.COL_SER,
                                                 colourBackground)

            self.gridDev.SetCellValue(i, self.COL_TUN, TUNER[device.tuner])
            self.gridDev.SetCellValue(i, self.COL_CAL, str(device.calibration))
            self.gridDev.SetCellValue(i, self.COL_LO, str(device.lo))
            self.gridDev.SetCellValue(i, self.COL_OFF, str(device.offset / 1e3))
            i += 1

        if self.settings.indexRtl >= len(self.devices):
            self.settings.indexRtl = len(self.devices) - 1
        self.__select_row(self.settings.indexRtl)
        self.index = self.settings.indexRtl

        self.gridDev.AutoSize()

    def __get_dev_grid(self):
        i = 0
        for device in self.devices:
            if not device.isDevice:
                server = self.gridDev.GetCellValue(i, self.COL_DEV)
                server = '//' + server
                url = urlparse(server)
                if url.hostname is not None:
                    device.server = url.hostname
                else:
                    device.server = 'localhost'
                if url.port is not None:
                    device.port = url.port
                else:
                    device.port = 1234
            device.gain = float(self.gridDev.GetCellValue(i, self.COL_GAIN))
            device.calibration = float(self.gridDev.GetCellValue(i, self.COL_CAL))
            device.lo = float(self.gridDev.GetCellValue(i, self.COL_LO))
            device.offset = float(self.gridDev.GetCellValue(i, self.COL_OFF)) * 1e3
            i += 1

    def __set_button_state(self):
        if len(self.devices) > 0:
            self.buttonDel.Enable()
        else:
            self.buttonDel.Disable()
        if len(self.devices) == 1:
            self.__select_row(0)

    def __warn_duplicates(self):
        servers = []
        for device in self.devices:
            if not device.isDevice:
                servers.append("{0}:{1}".format(device.server, device.port))

        dupes = set(servers)
        if len(dupes) != len(servers):
            message = "Duplicate server found:\n'{0}'".format(dupes.pop())
            dlg = wx.MessageDialog(self, message, "Warning",
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return True

        return False

    def __on_click(self, event):
        col = event.GetCol()
        index = event.GetRow()
        if col == self.COL_SEL:
            self.index = event.GetRow()
            self.__select_row(index)
        elif col == self.COL_OFF:
            device = self.devices[index]
            dlg = DialogOffset(self, device,
                               float(self.gridDev.GetCellValue(index,
                                                               self.COL_OFF)),
                               self.settings.winFunc)
            if dlg.ShowModal() == wx.ID_OK:
                self.gridDev.SetCellValue(index, self.COL_OFF,
                                          str(dlg.get_offset()))
            dlg.Destroy()
        else:
            self.gridDev.ForceRefresh()
            event.Skip()

        self.__set_button_state()

    def __on_add(self, _event):
        device = DeviceRTL()
        device.isDevice = False
        self.devices.append(device)
        self.gridDev.AppendRows(1)
        self.__set_dev_grid()
        self.SetSizerAndFit(self.devbox)
        self.__set_button_state()

    def __on_del(self, _event):
        del self.devices[self.index]
        self.gridDev.DeleteRows(self.index)
        self.__set_dev_grid()
        self.SetSizerAndFit(self.devbox)
        self.__set_button_state()

    def __on_ok(self, _event):
        self.__get_dev_grid()
        if self.__warn_duplicates():
            return
        self.EndModal(wx.ID_OK)

    def __select_row(self, index):
        self.gridDev.ClearSelection()
        for i in range(0, len(self.devices)):
            tick = "0"
            if i == index:
                tick = "1"
            self.gridDev.SetCellValue(i, self.COL_SEL, tick)

    def get_index(self):
        return self.index

    def get_devices(self):
        return self.devices


class DialogDevicesGPS(wx.Dialog):
    COL_SEL, COL_NAME, COL_TYPE, COL_HOST, COL_TEST = range(5)

    def __init__(self, parent, settings):
        self.settings = settings
        self.index = settings.indexGps
        self.devices = copy.copy(settings.devicesGps)
        self.comboType = None

        wx.Dialog.__init__(self, parent=parent, title="GPS Devices")

        self.checkGps = wx.CheckBox(self, wx.ID_ANY, "Enable GPS")
        self.checkGps.SetToolTip(wx.ToolTip('Record GPS locations in scans'))
        self.checkGps.SetValue(settings.gps)

        self.gridDev = grid.Grid(self)
        self.gridDev.CreateGrid(len(self.devices), 5)
        self.gridDev.SetRowLabelSize(0)
        self.gridDev.SetColLabelValue(self.COL_SEL, "Selected")
        self.gridDev.SetColLabelValue(self.COL_NAME, "Name")
        self.gridDev.SetColLabelValue(self.COL_HOST, "Host")
        self.gridDev.SetColLabelValue(self.COL_TYPE, "Type")
        self.gridDev.SetColLabelValue(self.COL_TEST, "Test")

        self.__set_dev_grid()

        sizerDevice = wx.BoxSizer(wx.HORIZONTAL)
        buttonAdd = wx.Button(self, wx.ID_ADD)
        self.buttonDel = wx.Button(self, wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self.__on_add, buttonAdd)
        self.Bind(wx.EVT_BUTTON, self.__on_del, self.buttonDel)
        sizerDevice.Add(buttonAdd, 0, wx.ALL)
        sizerDevice.Add(self.buttonDel, 0, wx.ALL)
        self.__set_button_state()

        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons = wx.StdDialogButtonSizer()
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        self.devbox = wx.BoxSizer(wx.VERTICAL)
        self.devbox.Add(self.checkGps, 0, wx.ALL | wx.EXPAND, 10)
        self.devbox.Add(self.gridDev, 1, wx.ALL | wx.EXPAND, 10)
        self.devbox.Add(sizerDevice, 0, wx.ALL | wx.EXPAND, 10)
        self.devbox.Add(sizerButtons, 0, wx.ALL | wx.EXPAND, 10)

        self.SetSizerAndFit(self.devbox)

    def __set_dev_grid(self):
        self.gridDev.Unbind(grid.EVT_GRID_EDITOR_CREATED)
        self.Unbind(grid.EVT_GRID_CELL_LEFT_CLICK)
        self.Unbind(grid.EVT_GRID_CELL_CHANGE)
        self.gridDev.ClearGrid()

        i = 0
        for device in self.devices:
            self.gridDev.SetReadOnly(i, self.COL_SEL, True)
            self.gridDev.SetCellRenderer(i, self.COL_SEL,
                                         TickCellRenderer())
            self.gridDev.SetCellValue(i, self.COL_NAME, device.name)
            cell = grid.GridCellChoiceEditor(sorted(DeviceGPS.TYPE),
                                             allowOthers=False)
            self.gridDev.SetCellValue(i, self.COL_TYPE,
                                      DeviceGPS.TYPE[device.type])
            self.gridDev.SetCellEditor(i, self.COL_TYPE, cell)

            if device.type == DeviceGPS.NMEA_SERIAL:
                self.gridDev.SetCellValue(i, self.COL_HOST,
                                          device.get_serial_desc())
                self.gridDev.SetReadOnly(i, self.COL_HOST, True)
            else:
                self.gridDev.SetCellValue(i, self.COL_HOST, device.resource)
                self.gridDev.SetReadOnly(i, self.COL_HOST, False)

            self.gridDev.SetCellValue(i, self.COL_TEST, '...')
            self.gridDev.SetCellAlignment(i, self.COL_SEL,
                                          wx.ALIGN_CENTRE, wx.ALIGN_CENTRE)
            i += 1

        self.index = limit(self.index, 0, len(self.devices) - 1)
        self.__select_row(self.index)
        self.index = self.index

        self.gridDev.AutoSize()

        self.gridDev.Bind(grid.EVT_GRID_EDITOR_CREATED, self.__on_create)
        self.Bind(grid.EVT_GRID_CELL_LEFT_CLICK, self.__on_click)
        self.Bind(grid.EVT_GRID_CELL_CHANGE, self.__on_change)

    def __set_button_state(self):
        if len(self.devices) > 0:
            self.buttonDel.Enable()
        else:
            self.buttonDel.Disable()
        if len(self.devices) == 1:
            self.__select_row(0)

    def __warn_duplicates(self):
        devices = []
        for device in self.devices:
            devices.append(device.name)

        dupes = set(devices)
        if len(dupes) != len(devices):
            message = "Duplicate name found:\n'{0}'".format(dupes.pop())
            dlg = wx.MessageDialog(self, message, "Warning",
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return True

        return False

    def __on_create(self, event):
        col = event.GetCol()
        index = event.GetRow()
        device = self.devices[index]
        if col == self.COL_TYPE:
            self.comboType = event.GetControl()
            self.comboType.Bind(wx.EVT_COMBOBOX,
                                lambda event,
                                device=device: self.__on_type(event, device))
        event.Skip()

    def __on_click(self, event):
        col = event.GetCol()
        index = event.GetRow()
        device = self.devices[index]
        if col == self.COL_SEL:
            self.index = event.GetRow()
            self.__select_row(index)
        elif col == self.COL_HOST:
            if device.type == DeviceGPS.NMEA_SERIAL:
                dlg = DialogGPSSerial(self, device)
                dlg.ShowModal()
                dlg.Destroy()
                self.gridDev.SetCellValue(index, self.COL_HOST,
                                          device.get_serial_desc())
            else:
                event.Skip()

        elif col == self.COL_TEST:
            dlg = DialogGPSTest(self, device)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            self.gridDev.ForceRefresh()
            event.Skip()

    def __on_change(self, event):
        col = event.GetCol()
        index = event.GetRow()
        device = self.devices[index]
        if col == self.COL_NAME:
            device.name = self.gridDev.GetCellValue(index, self.COL_NAME)
        elif col == self.COL_TYPE:
            device.type = DeviceGPS.TYPE.index(self.gridDev.GetCellValue(index,
                                                                         self.COL_TYPE))
            self.__set_dev_grid()
            self.SetSizerAndFit(self.devbox)
            event.Skip()
        elif col == self.COL_HOST:
            if device.type != DeviceGPS.NMEA_SERIAL:
                device.resource = self.gridDev.GetCellValue(index,
                                                            self.COL_HOST)

    def __on_type(self, event, device):
        device.type = DeviceGPS.TYPE.index(event.GetString())
        if device.type == DeviceGPS.NMEA_SERIAL:
            device.resource = get_serial_ports()[0]
        elif device.type == DeviceGPS.NMEA_TCP:
            device.resource = 'localhost:10110'
        else:
            device.resource = 'localhost:2947'

    def __on_add(self, _event):
        device = DeviceGPS()
        self.devices.append(device)
        self.gridDev.AppendRows(1)
        self.__set_dev_grid()
        self.SetSizerAndFit(self.devbox)
        self.__set_button_state()

    def __on_del(self, _event):
        del self.devices[self.index]
        self.gridDev.DeleteRows(self.index)
        self.__set_dev_grid()
        self.SetSizerAndFit(self.devbox)
        self.__set_button_state()

    def __on_ok(self, _event):
        if self.__warn_duplicates():
            return

        self.settings.gps = self.checkGps.GetValue()
        self.settings.devicesGps = self.devices
        if len(self.devices) == 0:
            self.index = -1
        self.settings.indexGps = self.index
        self.EndModal(wx.ID_OK)

    def __select_row(self, index):
        self.index = index
        self.gridDev.ClearSelection()
        for i in range(0, len(self.devices)):
            tick = "0"
            if i == index:
                tick = "1"
            self.gridDev.SetCellValue(i, self.COL_SEL, tick)


class DialogGPSSerial(wx.Dialog):
    def __init__(self, parent, device):
        self.device = device
        self.ports = get_serial_ports()

        wx.Dialog.__init__(self, parent=parent, title='Serial port settings')

        textPort = wx.StaticText(self, label='Port')
        self.choicePort = wx.Choice(self, choices=self.ports)
        sel = 0
        if device.resource in self.ports:
            sel = self.ports.index(device.resource)
        self.choicePort.SetSelection(sel)

        textBaud = wx.StaticText(self, label='Baud rate')
        self.choiceBaud = wx.Choice(self,
                                    choices=[str(baud) for baud in DeviceGPS.BAUDS])
        self.choiceBaud.SetSelection(DeviceGPS.BAUDS.index(device.baud))
        textByte = wx.StaticText(self, label='Byte size')
        self.choiceBytes = wx.Choice(self,
                                     choices=[str(byte) for byte in DeviceGPS.BYTES])
        self.choiceBytes.SetSelection(DeviceGPS.BYTES.index(device.bytes))
        textParity = wx.StaticText(self, label='Parity')
        self.choiceParity = wx.Choice(self, choices=DeviceGPS.PARITIES)
        self.choiceParity.SetSelection(DeviceGPS.PARITIES.index(device.parity))
        textStop = wx.StaticText(self, label='Stop bits')
        self.choiceStops = wx.Choice(self,
                                     choices=[str(stop) for stop in DeviceGPS.STOPS])
        self.choiceStops.SetSelection(DeviceGPS.STOPS.index(device.stops))
        textSoft = wx.StaticText(self, label='Software flow control')
        self.checkSoft = wx.CheckBox(self)
        self.checkSoft.SetValue(device.soft)

        buttonOk = wx.Button(self, wx.ID_OK)
        buttonCancel = wx.Button(self, wx.ID_CANCEL)
        sizerButtons = wx.StdDialogButtonSizer()
        sizerButtons.AddButton(buttonOk)
        sizerButtons.AddButton(buttonCancel)
        sizerButtons.Realize()
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        grid = wx.GridBagSizer(10, 10)
        grid.Add(textPort, pos=(0, 0), flag=wx.ALL)
        grid.Add(self.choicePort, pos=(0, 1), flag=wx.ALL)
        grid.Add(textBaud, pos=(1, 0), flag=wx.ALL)
        grid.Add(self.choiceBaud, pos=(1, 1), flag=wx.ALL)
        grid.Add(textByte, pos=(2, 0), flag=wx.ALL)
        grid.Add(self.choiceBytes, pos=(2, 1), flag=wx.ALL)
        grid.Add(textParity, pos=(3, 0), flag=wx.ALL)
        grid.Add(self.choiceParity, pos=(3, 1), flag=wx.ALL)
        grid.Add(textStop, pos=(4, 0), flag=wx.ALL)
        grid.Add(self.choiceStops, pos=(4, 1), flag=wx.ALL)
        grid.Add(textSoft, pos=(5, 0), flag=wx.ALL)
        grid.Add(self.checkSoft, pos=(5, 1), flag=wx.ALL)

        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(grid, flag=wx.ALL, border=10)
        box.Add(sizerButtons, flag=wx.ALL | wx.ALIGN_RIGHT, border=10)

        self.SetSizerAndFit(box)

    def __on_ok(self, _event):
        self.device.resource = self.ports[self.choicePort.GetSelection()]
        self.device.baud = DeviceGPS.BAUDS[self.choiceBaud.GetSelection()]
        self.device.bytes = DeviceGPS.BYTES[self.choiceBytes.GetSelection()]
        self.device.parity = DeviceGPS.PARITIES[self.choiceParity.GetSelection()]
        self.device.stops = DeviceGPS.STOPS[self.choiceStops.GetSelection()]
        self.device.soft = self.checkSoft.GetValue()

        self.EndModal(wx.ID_OK)


class DialogGPSTest(wx.Dialog):
    POLL = 500

    def __init__(self, parent, device):
        self.device = device
        self.threadLocation = None
        self.raw = ''

        wx.Dialog.__init__(self, parent=parent, title='GPS Test')

        textLat = wx.StaticText(self, label='Longitude')
        self.textLat = wx.TextCtrl(self, style=wx.TE_READONLY)
        textLon = wx.StaticText(self, label='Latitude')
        self.textLon = wx.TextCtrl(self, style=wx.TE_READONLY)
        textAlt = wx.StaticText(self, label='Altitude')
        self.textAlt = wx.TextCtrl(self, style=wx.TE_READONLY)
        textSats = wx.StaticText(self, label='Satellites')
        self.textSats = wx.TextCtrl(self, style=wx.TE_READONLY)
        textRaw = wx.StaticText(self, label='Raw output')
        self.textRaw = wx.TextCtrl(self,
                                   style=wx.TE_MULTILINE | wx.TE_READONLY)

        textLevel = wx.StaticText(self, label='Level')
        self.satLevel = SatLevel(self)

        self.buttonStart = wx.Button(self, label='Start')
        self.Bind(wx.EVT_BUTTON, self.__on_start, self.buttonStart)
        self.buttonStop = wx.Button(self, label='Stop')
        self.Bind(wx.EVT_BUTTON, self.__on_stop, self.buttonStop)
        self.buttonStop.Disable()

        buttonOk = wx.Button(self, wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.__on_ok, buttonOk)

        grid = wx.GridBagSizer(10, 10)

        grid.Add(textLat, pos=(0, 0), flag=wx.ALL, border=5)
        grid.Add(self.textLat, pos=(0, 1), span=(1, 2), flag=wx.ALL, border=5)
        grid.Add(textLon, pos=(1, 0), flag=wx.ALL, border=5)
        grid.Add(self.textLon, pos=(1, 1), span=(1, 2), flag=wx.ALL, border=5)
        grid.Add(textAlt, pos=(2, 0), flag=wx.ALL, border=5)
        grid.Add(self.textAlt, pos=(2, 1), span=(1, 2), flag=wx.ALL, border=5)
        grid.Add(textSats, pos=(3, 0), flag=wx.ALL, border=5)
        grid.Add(self.textSats, pos=(3, 1), span=(1, 2), flag=wx.ALL, border=5)
        grid.Add(textLevel, pos=(0, 3), flag=wx.ALL, border=5)
        grid.Add(self.satLevel, pos=(1, 3), span=(3, 2), flag=wx.ALL, border=5)
        grid.Add(textRaw, pos=(4, 0), flag=wx.ALL, border=5)
        grid.Add(self.textRaw, pos=(5, 0), span=(5, 5),
                 flag=wx.ALL | wx.EXPAND, border=5)
        grid.Add(self.buttonStart, pos=(10, 2), flag=wx.ALL, border=5)
        grid.Add(self.buttonStop, pos=(10, 3), flag=wx.ALL | wx.ALIGN_RIGHT,
                 border=5)
        grid.Add(buttonOk, pos=(11, 4), flag=wx.ALL | wx.ALIGN_RIGHT,
                 border=5)

        self.SetSizerAndFit(grid)

        self.queue = Queue.Queue()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.__on_timer, self.timer)
        self.timer.Start(self.POLL)

    def __on_start(self, _event):
        if not self.threadLocation:
            self.buttonStart.Disable()
            self.buttonStop.Enable()
            self.textRaw.SetValue('')
            self.__add_raw('Starting...')
            self.threadLocation = ThreadLocation(self.queue, self.device,
                                                 raw=True)

    def __on_stop(self, _event):
        if self.threadLocation and self.threadLocation.isAlive():
            self.__add_raw('Stopping...')
            self.threadLocation.stop()
            self.threadLocation.join()
        self.threadLocation = None
        self.buttonStart.Enable()
        self.buttonStop.Disable()

    def __on_ok(self, _event):
        self.__on_stop(None)
        self.EndModal(wx.ID_OK)

    def __on_timer(self, _event):
        self.timer.Stop()
        while not self.queue.empty():
            event = self.queue.get()
            status = event.data.get_status()
            loc = event.data.get_arg2()

            if status == Event.LOC:
                if loc[0] is not None:
                    text = '{:.5f}'.format(loc[0])
                else:
                    text = ''
                self.textLon.SetValue(text)
                if loc[1] is not None:
                    text = '{:.5f}'.format(loc[1])
                else:
                    text = ''
                self.textLat.SetValue(text)
                if loc[2] is not None:
                    text = '{:.1f}'.format(loc[2])
                else:
                    text = ''
                self.textAlt.SetValue(text)
            elif status == Event.LOC_SAT:
                self.satLevel.set_sats(loc)
                used = sum(1 for sat in loc.values() if sat[1])
                self.textSats.SetLabel('{}/{}'.format(used, len(loc)))
            elif status == Event.LOC_ERR:
                self.__on_stop(None)
                self.__add_raw('{0}'.format(loc))
            elif status == Event.LOC_RAW:
                self.__add_raw(loc)
        self.timer.Start(self.POLL)

    def __add_raw(self, text):
        text = text.replace('\n', '')
        text = text.replace('\r', '')
        terminal = self.textRaw.GetValue().split('\n')
        terminal.append(text)
        while len(terminal) > 100:
            terminal.pop(0)
        self.textRaw.SetValue('\n'.join(terminal))
        self.textRaw.ScrollPages(self.textRaw.GetNumberOfLines())


class DialogSats(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent=parent, title='GPS Satellite Levels')
        self.parent = parent

        self.satLevel = SatLevel(self)

        self.textSats = wx.StaticText(self)
        self.__set_text(0, 0)

        self.Bind(wx.EVT_CLOSE, self.__on_close)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.satLevel, 1, flag=wx.ALL | wx.EXPAND, border=5)
        sizer.Add(self.textSats, 0, flag=wx.ALL | wx.EXPAND, border=5)

        self.SetSizerAndFit(sizer)

    def __set_text(self, used, seen):
        self.textSats.SetLabel('Satellites: {} used, {} seen'.format(used,
                                                                     seen))

    def __on_close(self, _event):
        self.Unbind(wx.EVT_CLOSE)
        self.parent.dlgSats = None
        self.Close()

    def set_sats(self, sats):
        self.satLevel.set_sats(sats)
        used = sum(1 for sat in sats.values() if sat[1])
        self.__set_text(used, len(sats))


class DialogSaveWarn(wx.Dialog):
    def __init__(self, parent, warnType):
        self.code = -1

        wx.Dialog.__init__(self, parent=parent, title="Warning")

        prompt = ["scanning again", "opening a file",
                  "exiting", "clearing"][warnType]
        text = wx.StaticText(self,
                             label="Save plot_line before {0}?".format(prompt))
        icon = wx.StaticBitmap(self, wx.ID_ANY,
                               wx.ArtProvider.GetBitmap(wx.ART_INFORMATION,
                                                        wx.ART_MESSAGE_BOX))

        tbox = wx.BoxSizer(wx.HORIZONTAL)
        tbox.Add(text)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(icon, 0, wx.ALL, 5)
        hbox.Add(tbox, 0, wx.ALL, 5)

        buttonYes = wx.Button(self, wx.ID_YES, 'Yes')
        buttonNo = wx.Button(self, wx.ID_NO, 'No')
        buttonCancel = wx.Button(self, wx.ID_CANCEL, 'Cancel')

        buttonYes.Bind(wx.EVT_BUTTON, self.__on_close)
        buttonNo.Bind(wx.EVT_BUTTON, self.__on_close)

        buttons = wx.StdDialogButtonSizer()
        buttons.AddButton(buttonYes)
        buttons.AddButton(buttonNo)
        buttons.AddButton(buttonCancel)
        buttons.Realize()

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(hbox, 1, wx.ALL | wx.EXPAND, 10)
        vbox.Add(buttons, 1, wx.ALL | wx.EXPAND, 10)

        self.SetSizerAndFit(vbox)

    def __on_close(self, event):
        self.EndModal(event.GetId())
        return

    def get_code(self):
        return self.code


class DialogRefresh(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent=parent, style=0)

        text = wx.StaticText(self, label="Refreshing plot_line, please wait...")
        icon = wx.StaticBitmap(self, wx.ID_ANY,
                               wx.ArtProvider.GetBitmap(wx.ART_INFORMATION,
                                                        wx.ART_MESSAGE_BOX))

        box = wx.BoxSizer(wx.HORIZONTAL)
        box.Add(icon, flag=wx.ALIGN_CENTRE | wx.ALL, border=10)
        box.Add(text, flag=wx.ALIGN_CENTRE | wx.ALL, border=10)

        self.SetSizerAndFit(box)
        self.Centre()


class DialogSysInfo(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent=parent, title="Software Versions")

        textVersions = wx.TextCtrl(self,
                                   style=wx.TE_MULTILINE |
                                   wx.TE_READONLY |
                                   wx.TE_DONTWRAP |
                                   wx.TE_NO_VSCROLL)
        buttonOk = wx.Button(self, wx.ID_OK)

        self.__populate_versions(textVersions)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(textVersions, 1, flag=wx.ALL, border=10)
        sizer.Add(buttonOk, 0, flag=wx.ALL | wx.ALIGN_RIGHT, border=10)
        self.SetSizerAndFit(sizer)
        self.Centre()

    def __populate_versions(self, control):
        imageType = 'Pillow'
        try:
            imageVer = Image.PILLOW_VERSION
        except AttributeError:
            imageType = 'PIL'
            imageVer = Image.VERSION

        versions = ('Hardware:\n'
                    '\tProcessor: {}, {} cores\n\n'
                    'Software:\n'
                    '\tOS: {}, {}\n'
                    '\tPython: {}\n'
                    '\tmatplotlib: {}\n'
                    '\tNumPy: {}\n'
                    '\t{}: {}\n'
                    '\tpySerial: {}\n'
                    '\twxPython: {}\n'
                    ).format(platform.processor(), multiprocessing.cpu_count(),
                             platform.platform(), platform.machine(),
                             platform.python_version(),
                             matplotlib.__version__,
                             numpy.version.version,
                             imageType, imageVer,
                             serial.VERSION,
                             wx.version())

        control.SetValue(versions)

        dc = wx.WindowDC(control)
        extent = list(dc.GetMultiLineTextExtent(versions, control.GetFont()))
        extent[0] += wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X) * 2
        extent[1] += wx.SystemSettings.GetMetric(wx.SYS_HSCROLL_Y) * 2
        control.SetMinSize((extent[0], extent[1]))
        self.Layout()


class DialogAbout(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent=parent, title="About")

        bitmapIcon = wx.StaticBitmap(self, bitmap=load_bitmap('icon'))
        textAbout = wx.StaticText(self, label="A simple spectrum analyser for "
                                  "scanning\n with a RTL-SDR compatible USB "
                                  "device", style=wx.ALIGN_CENTRE)
        textLink = wx.HyperlinkCtrl(self, wx.ID_ANY,
                                    label="http://eartoearoak.com/software/rtlsdr-scanner",
                                    url="http://eartoearoak.com/software/rtlsdr-scanner")
        textTimestamp = wx.StaticText(self,
                                      label="Updated: " + get_version_timestamp())
        buttonOk = wx.Button(self, wx.ID_OK)

        grid = wx.GridBagSizer(10, 10)
        grid.Add(bitmapIcon, pos=(0, 0), span=(3, 1),
                 flag=wx.ALIGN_LEFT | wx.ALL, border=10)
        grid.Add(textAbout, pos=(0, 1), span=(1, 2),
                 flag=wx.ALIGN_CENTRE | wx.ALL, border=10)
        grid.Add(textLink, pos=(1, 1), span=(1, 2),
                 flag=wx.ALIGN_CENTRE | wx.ALL, border=10)
        grid.Add(textTimestamp, pos=(2, 1), span=(1, 2),
                 flag=wx.ALIGN_CENTRE | wx.ALL, border=10)
        grid.Add(buttonOk, pos=(3, 2), span=(1, 1),
                 flag=wx.ALIGN_RIGHT | wx.ALL, border=10)

        self.SetSizerAndFit(grid)
        self.Centre()


class DialogLog(wx.Dialog):
    def __init__(self, parent, log):
        wx.Dialog.__init__(self, parent=parent, title="Log")

        self.parent = parent
        self.log = log

        self.gridLog = grid.Grid(self)
        self.gridLog.CreateGrid(log.MAX_ENTRIES, 3)
        self.gridLog.SetRowLabelSize(0)
        self.gridLog.SetColLabelValue(0, "Time")
        self.gridLog.SetColLabelValue(1, "Level")
        self.gridLog.SetColLabelValue(2, "Event")
        self.gridLog.EnableEditing(False)

        textFilter = wx.StaticText(self, label='Level')
        self.choiceFilter = wx.Choice(self,
                                      choices=['All'] + self.log.TEXT_LEVEL)
        self.choiceFilter.SetSelection(0)
        self.choiceFilter.SetToolTipString('Filter log level')
        self.Bind(wx.EVT_CHOICE, self.__on_filter, self.choiceFilter)
        sizerFilter = wx.BoxSizer()
        sizerFilter.Add(textFilter, flag=wx.ALL, border=5)
        sizerFilter.Add(self.choiceFilter, flag=wx.ALL, border=5)

        buttonRefresh = wx.Button(self, wx.ID_ANY, label='Refresh')
        buttonRefresh.SetToolTipString('Refresh the log')
        buttonClose = wx.Button(self, wx.ID_CLOSE)
        self.Bind(wx.EVT_BUTTON, self.__on_refresh, buttonRefresh)
        self.Bind(wx.EVT_BUTTON, self.__on_close, buttonClose)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.gridLog, 1, flag=wx.ALL | wx.EXPAND, border=5)
        sizer.Add(sizerFilter, 0, flag=wx.ALL, border=5)
        sizer.Add(buttonRefresh, 0, flag=wx.ALL, border=5)
        sizer.Add(buttonClose, 0, flag=wx.ALL | wx.ALIGN_RIGHT, border=5)

        self.sizer = sizer
        self.__update_grid()
        self.SetSizer(sizer)

        self.Bind(wx.EVT_CLOSE, self.__on_close)

    def __on_filter(self, _event):
        selection = self.choiceFilter.GetSelection()
        if selection == 0:
            level = None
        else:
            level = selection - 1
        self.__update_grid(level)

    def __on_refresh(self, _event):
        self.__update_grid()

    def __on_close(self, _event):
        self.Unbind(wx.EVT_CLOSE)
        self.parent.dlgLog = None
        self.Close()

    def __update_grid(self, level=None):
        self.gridLog.ClearGrid()

        fontCell = self.gridLog.GetDefaultCellFont()
        fontSize = fontCell.GetPointSize()
        fontStyle = fontCell.GetStyle()
        fontWeight = fontCell.GetWeight()
        font = wx.Font(fontSize, wx.FONTFAMILY_MODERN, fontStyle,
                       fontWeight)

        i = 0
        for event in self.log.get(level):
            self.gridLog.SetCellValue(i, 0, format_time(event[0], True))
            self.gridLog.SetCellValue(i, 1, self.log.TEXT_LEVEL[event[1]])
            eventText = '\n'.join(textwrap.wrap(event[2], width=70))
            self.gridLog.SetCellValue(i, 2, eventText)
            self.gridLog.SetCellFont(i, 0, font)
            self.gridLog.SetCellFont(i, 1, font)
            self.gridLog.SetCellFont(i, 2, font)
            self.gridLog.SetCellAlignment(i, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTRE)
            self.gridLog.SetCellAlignment(i, 1, wx.ALIGN_LEFT, wx.ALIGN_CENTRE)
            i += 1

        self.gridLog.AppendRows()
        self.gridLog.SetCellValue(i, 0, '#' * 18)
        self.gridLog.SetCellValue(i, 1, '#' * 5)
        self.gridLog.SetCellValue(i, 2, '#' * 80)
        self.gridLog.AutoSize()
        self.gridLog.DeleteRows(i)

        size = self.gridLog.GetBestSize()
        size.width += wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X) + 10
        size.height = 400
        self.SetClientSize(size)
        self.sizer.Layout()


if __name__ == '__main__':
    print 'Please run rtlsdr_scan.py'
    exit(1)
