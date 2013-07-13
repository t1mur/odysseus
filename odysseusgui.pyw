#!/usr/bin/env python
# This program or module is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 2 of the License, or
# version 3 of the License.
# See the GNU General Public License for more details.


import sys
import os
import time
import platform
import glob
import cgitb # html formatting of tracebacks
import webbrowser

import numpy as np
import matplotlib as mpl
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import dirmonitor
from imageprocess import calc_absimage
import imageio
import filetools
from fitfermions import fit_img, find_ellipticity
import qrcresources
import pluginmanager
from mplwidgets import *
from guihelpfuncs import *


__version__ = "0.4.0"
cgitb.enable(display=0, logdir='logs', context=1)


class Fitter(QThread):
    """This class runs the fitting routines. This keeps the GUI responsive."""

    def __init__(self, img, parent=None):
        super(Fitter, self).__init__(parent)
        self.img = img
        self.func = 'idealfermi'
        self.check_ellipse = False


    def run(self):
        """Is called by QThread.start(), when returning stops complete thread"""

        try:
            if self.check_ellipse:
                elliptic = (find_ellipticity(self.img), 0)
            else:
                elliptic = None

            fitresult = fit_img(self.img, showfig=False, full_output='odysseus',
                                fitfunc=self.func, elliptic=elliptic)
            self.emit(SIGNAL("fitresult"), fitresult)

        except ValueError:
            failmsg = 'Fitting failed - is the analysis ROI set correctly?'
            self.emit(SIGNAL("fitresult"), failmsg)


class GuiFitfuncs():
    def __init__(self, com, numatoms, temp, cloudsize):
        """Create reference to gui info boxes, and fit function dict.

        All fit functions that are available should be added to self.funcs,
        they will then automatically show up in the GUI. The fit function is
        defined here, of course the fitting is done in fitfermions.py. In
        that file fit_img and do_fit should be modified so the return values
        make sense.

        """

        self.com = com
        self.numatoms = numatoms
        self.temp = temp
        self.cloudsize = cloudsize
        self.roi = None
        self.txtfilename = None

        self.funcs = [{'name':'idealfermi', 'desc':'ideal Fermi gas',
                       'func':self.idealfermi},
                      {'name':'gaussian', 'desc':'Gaussian',
                       'func':self.gaussian},
                      {'name':'idealfermi_err', 'desc': 'ideal Fermi errorbar',
                       'func':self.idealfermi_err}]
        self.current_func = None
        self.current_datafilename = None


    def idealfermi(self, fig, fitresult):
        """Plot the OD and fitted profiles for fit with ideal Fermi gas"""

        ToverTF, N, com, fitparams, rcoord, od_prof, fit_prof = fitresult

        fig.ax.plot(rcoord, od_prof, 'k', lw=0.75)
        fig.ax.hold(True)
        fig.ax.plot(rcoord, fit_prof, '#FFAF7A', lw=1)
        fig.ax.hold(False)
        fig.ax.set_xlabel(r'$r$ [pix]')
        fig.ax.set_ylabel(r'$OD$')
        fig.draw()

        try:
            self._update_infoboxes(com, N, ToverTF, fitparams[2])
        except TypeError:
            pass


    def gaussian(self, fig, fitresult):
        """Plot the OD and fitted profiles for fit with a Gaussian"""

        ToverTF, N, com, fitparams, rcoord, od_prof, fit_prof = fitresult

        fig.ax.plot(rcoord, od_prof, 'k', lw=0.75)
        fig.ax.hold(True)
        fig.ax.plot(rcoord, fit_prof, '#FFAF7A', lw=1)
        fig.ax.hold(False)
        fig.ax.set_xlabel(r'$r$ [pix]')
        fig.ax.set_ylabel(r'$OD$')
        fig.draw()

        try:
            self._update_infoboxes(com, N, ToverTF, fitparams[1])
        except TypeError:
            pass


    def idealfermi_err(self, fig, fitresult):
        """Plot OD fitted and err profiles for fit with ideal Fermi gas"""

        ToverTF, N, com, fitparams, rcoord, od_prof, fit_prof, errprof_plus, \
               errprof_min = fitresult

        fig.ax.plot(rcoord, od_prof, 'k', lw=0.75)
        fig.ax.hold(True)
        fig.ax.plot(rcoord, fit_prof, '#FFAF7A', lw=1)
        fig.ax.plot(rcoord, errprof_plus, '#FFAF7A', lw=0.75, ls='--')
        fig.ax.plot(rcoord, errprof_min, '#FFAF7A', lw=0.75, ls='--')
        fig.ax.hold(False)
        fig.ax.set_xlabel(r'$r$ [pix]')
        fig.ax.set_ylabel(r'$OD$')
        fig.draw()

        try:
            self._update_infoboxes(com, N, ToverTF, fitparams[0][2])
        except TypeError:
            pass


    def _update_infoboxes(self, com, N, ToverTF, cloudsize):
        com = (com[1] + self.roi[0], com[0] + self.roi[2]) # inverted axes crap
        self.com.setText('(%1.1f, %1.1f)'%(com[0], com[1]))
        self.numatoms.setText('%1.2f million'%(N*1e-6))
        self.temp.setText('%1.2f T/T_F'%ToverTF)
        self.cloudsize.setText('%1.1f'%cloudsize)

        self._result_to_textfile(N, ToverTF)


    def _result_to_textfile(self, N, ToverTF):
        """Writes the fit result to a text file, to log results"""
        try:
            f = open(self.txtfilename, mode='a')
        except TypeError:
            return
        try:
            timestr = time.strftime('%H:%M:%S')
            fname = os.path.split(self.current_datafilename)[1]
            f.write('%1.3f    %1.3f    %s    %s\n'%(N*1e-6, ToverTF,
                                                    timestr, fname))
        finally:
            f.close()



class CentralWidget(QWidget):

    def __init__(self, parent=None):
        super(CentralWidget, self).__init__(parent)

        self.pathLabel, pathLayout = create_labeledbox('Monitoring path:',
                                                       stretch=1)
        self.pathButton = QPushButton("Set &Path...")
        pathLayout.addWidget(self.pathButton)

        # add first absorption image
        self.absImage = SingleImageCanvas()
        self.absImage.setCursor(Qt.CrossCursor)
        # label with data for crosshair marker
        self.absMarker = ImageMarker()
        palette3 = QPalette()
        palette3.setColor(QPalette.WindowText,
                          QColor.fromRgb(*coldict_rgb['lightblue']))
        self.absMarker.setPalette(palette3)
        # add toolbar
        toolbar = MyQTToolbar(self.absImage, self)

        ## the info widget ##
        # center of mass
        self.com, comLayout = create_labeledbox('Center of mass:')
        # cloud size
        self.cloudsize, cloudsizeLayout = create_labeledbox('Cloud size [pix]:')
        # number of atoms
        self.numatoms, numatomsLayout = create_labeledbox('Number of atoms:')
        # temperature
        self.temp, tempLayout = create_labeledbox('Temperature:')
        # ROI boxes
        self.roiAnalysis, self.roiAnInputs, self.setRoiAnalysis, \
            self.clearRoiAnalysis, self.roiAnLabels = create_roibox('Analysis ROI')
        self.roiNcount, self.roiNinputs, self.setRoiNcount, self.clearRoiNcount,\
            self.roiNLabels = create_roibox('Ncount ROI')
        # color ROI labels
        palette = QPalette()
        palette.setBrush(QPalette.WindowText, Qt.blue)
        self.roiAnalysis.setPalette(palette)
        palette2 = QPalette()
        palette2.setColor(QPalette.WindowText, \
                          QColor.fromRgb(*coldict_rgb['purple']))
        self.roiNcount.setPalette(palette2)
        self.imgctrlbox = ImgCtrlBox(self.absImage.colmaps)

        # fit controls
        self.ellipseCalc = QCheckBox('Calc ellipticity')
        self.autoFit = QCheckBox('Autofit')
        self.guifitfuncs = GuiFitfuncs(self.com, self.numatoms, self.temp,
                                       self.cloudsize)
        self.fitFunc = QComboBox()
        for fitfunc in self.guifitfuncs.funcs:
            self.fitFunc.addItem(fitfunc['desc'])
        self.fitForceButton = QPushButton('Fit now')
        # the figure
        self.plotFigure = InfoPlotCanvas()
        toolbar2 = NavigationToolbar2QT(self.plotFigure, self)

        # infobox layouts
        roigridLayout = QGridLayout()
        roigridLayout.addWidget(self.imgctrlbox.colbox, 0, 0)
        roigridLayout.addWidget(self.roiAnalysis, 0, 1)
        roigridLayout.addWidget(self.roiNcount, 1, 1)

        fitinfoLayout = QVBoxLayout()
        fitinfoLayout.addLayout(comLayout)
        fitinfoLayout.addLayout(cloudsizeLayout)
        fitinfoLayout.addLayout(numatomsLayout)
        fitinfoLayout.addLayout(tempLayout)

        fitLayout = QVBoxLayout()
        fitLayout.addWidget(self.ellipseCalc)
        fitLayout.addWidget(self.autoFit)
        fitLayout.addWidget(self.fitFunc)
        fitLayout.addWidget(self.fitForceButton)

        infoLayout = QVBoxLayout()
        infoLayout.addWidget(self.plotFigure)
        infoLayout.addWidget(toolbar2)

        roigridLayout.addLayout(fitLayout, 2, 0)
        roigridLayout.addLayout(fitinfoLayout, 2, 1)
        roigridLayout.addLayout(infoLayout, 3, 0, 1, 2)
        roigridLayout.setRowStretch(3, 1)

        self.infobox = QGroupBox('Current Image Info')
        self.infobox.setLayout(roigridLayout)

        # all the other layout stuff #
        absLayout = QVBoxLayout()
        self.absLabel = QLabel('Current image')
        self.cycleButton = QPushButton('+')
        absTopLayout = QHBoxLayout()
        absTopLayout.addWidget(self.absLabel)
        absTopLayout.addStretch()
        absTopLayout.addWidget(self.absMarker)
        absTopLayout.addWidget(self.cycleButton)
        absLayout.addLayout(absTopLayout)
        absLayout.addWidget(self.absImage)
        absLayout.addWidget(toolbar)

        imageLayout = QHBoxLayout()
        imageLayout.addLayout(absLayout)
        imageLayout.addStretch()

        middleLayout = QVBoxLayout()
        middleLayout.addLayout(pathLayout)
        middleLayout.addLayout(imageLayout)
        middleLayout.addStretch()

        mainLayout = QHBoxLayout()
        mainLayout.addLayout(middleLayout)
        mainLayout.addStretch()
        mainLayout.addWidget(self.infobox)

        # now add the image grid #
        self.gridImages = []
        self.gridnum = 8
        bottomLayout = QHBoxLayout()
        for i in range(self.gridnum):
            self.gridImages.append(PngWidget(":/blankimg.png", None,
                                             0, gridindex=i))
            bottomLayout.addWidget(self.gridImages[i])
            bottomLayout.addStretch()

        self.gridImageWidget = QGroupBox('Recent image history')
        self.gridImageWidget.setLayout(bottomLayout)

        layout = QVBoxLayout()
        layout.addLayout(mainLayout, 1)
        layout.addWidget(self.gridImageWidget)
        self.setLayout(layout)

        # signal-slot stuff #
        self.connect(self.setRoiNcount, SIGNAL("clicked()"), self.drawROI)
        self.connect(self.clearRoiNcount, SIGNAL("clicked()"), self.clearROI)
        self.connect(self.setRoiAnalysis, SIGNAL("clicked()"), self.drawROI)
        self.connect(self.clearRoiAnalysis, SIGNAL("clicked()"), self.clearROI)
        self.connect(self.imgctrlbox.setVals, SIGNAL("clicked()"),
                     self.setImgLimits)
        self.connect(self.imgctrlbox.colmapCtrl,
                     SIGNAL("currentIndexChanged(QString)"),
                     self.updateColormap)

        self.connect(self.absMarker, SIGNAL("ClearMarker"),
                     self.absImage.clearMarker)
        self.connect(self.absImage, SIGNAL("MarkerPixval"),
                     self.updateMarkerval)
        self.connect(self.cycleButton, SIGNAL("clicked()"), self.cycleImages)
        self.connect(self.fitForceButton, SIGNAL("clicked()"), self.fitImage)
        self.connect(self.absImage, SIGNAL("SizeChange"), self.update)
        for png in self.gridImages:
            self.connect(png, SIGNAL("updateAbsImage"), self.updateAbsImage)

        # updating ROI coordinates through right-clicking on labels
        self.connect(self.roiAnLabels[0], SIGNAL("LabelMsg"), self.setRoiCoords)
        self.connect(self.roiAnLabels[1], SIGNAL("LabelMsg"), self.setRoiCoords)
        self.connect(self.roiNLabels[0], SIGNAL("LabelMsg"), self.setRoiCoords)
        self.connect(self.roiNLabels[1], SIGNAL("LabelMsg"), self.setRoiCoords)

        self.setMouseTracking(True)


    def mouseMoveEvent(self, event):
        """Restores the normal cursor"""
        QApplication.restoreOverrideCursor()


    def load_imgs(self, path):
        """Loads images from path"""

        img_list = []
        ncount = []
        pnglist = []

        imgs_sorted = filetools.get_files_in_dir(str(path))

        # load as much images as fit in the GUI, if possible
        self.numload = min(self.gridnum, len(imgs_sorted))
        self.datafilelist = imgs_sorted[:self.numload]
        for item in self.datafilelist:
            QApplication.processEvents() # update GUI, keep it responsive

            rawdata = imageio.imgimport_intelligent(item)
            # calculate transmission image and OD
            if rawdata is not None:
                transimg, odimg = calc_absimage(rawdata)
                pnglist.append(save_png(transimg, *(os.path.split(item))))
                img = np.zeros((rawdata.shape[0], rawdata.shape[1],
                                rawdata.shape[2]+1), dtype=np.float32)
                img[:, :, 0] = transimg
                img[:, :, 1:] = rawdata
                img_list.append(img)
                roi = self.absImage.getImgROI('ncount')[1]
                if roi:
                    odimg = odimg[roi[2]:roi[3], roi[0]:roi[1]]
                ncount.append(odimg.sum())
            else:
                msg = "Warning: TIF image does not contain 3 frames"
                self.emit(SIGNAL("updateStatusBar"), msg)
            self.emit(SIGNAL("updateProgressBar"), len(ncount))

        self.img_list = img_list
        self.ncount = ncount
        self.pnglist = pnglist

        if not imgs_sorted:
            msg =  "No suitable images found"
            self.emit(SIGNAL("updateStatusBar"), msg)


    def load_newimg(self, fpathname):
        """Loads new image from path"""

        fpathname = str(fpathname)
        file_ext = os.path.splitext(fpathname)[1]
        if file_ext=='.TIF':
            rawdata = imageio.imgimport_intelligent(fpathname)
        elif file_ext=='.xraw0':
            rawdata = imageio.import_xcamera(fpathname)
        else:
            msg = 'File does not have a valid extension'
            self.emit(SIGNAL("updateStatusBar"), msg)

        # calculate transmission image and OD
        if rawdata is not None:
            transimg, odimg = calc_absimage(rawdata)
            pngname = save_png(transimg, *(os.path.split(fpathname)))
            self.rawdata = rawdata

            try:
                if len(self.img_list)==self.gridnum:
                    # remove last image from list
                    self.img_list.pop()
                    self.ncount.pop()
                    self.pnglist.pop()
                    self.datafilelist.pop()
            except AttributeError:
                self.img_list = []
                self.ncount = []
                self.pnglist = []
            img = np.zeros((rawdata.shape[0], rawdata.shape[1],
                            rawdata.shape[2]+1), dtype=np.float32)
            img[:, :, 0] = transimg
            img[:, :, 1:] = rawdata
            self.img_list.insert(0, img)
            roi = self.absImage.getImgROI('ncount')[1]
            if roi:
                odimg = odimg[roi[2]:roi[3], roi[0]:roi[1]]
            self.ncount.insert(0, odimg.sum())
            self.pnglist.insert(0, pngname)
            self.datafilelist.insert(0, fpathname)
            self.numload = min(self.gridnum, len(self.img_list))
        else:
            msg = "Warning: TIF image does not contain 3 frames"
            self.emit(SIGNAL("updateStatusBar"), msg)


    def display_imgs(self):
        """Updates the GUI with new images."""

        if self.img_list:
            self.absImage.img = self.img_list[0]
            self.absImage.datafilepath = self.datafilelist[0]
            self.absImage.update_img()
            if self.autoFit.isChecked():
                self.fitImage()
        try:
            for i in range(self.numload):
                self.gridImages[i].update(self.pnglist[i], self.datafilelist[i],
                                          self.ncount[i])
        except IndexError:
            # when there are no more images left to display, stop
            pass


    def update_gridimgs(self):
        """Updates the grid images in an efficient way.

        One image is prepended to the grid, the last one is removed.
        This should be a few seconds faster than redrawing everything.
        """

        self.bottomLayout.removeWidget(self.gridImages[-1])
        del self.gridImages[-1]
        pass


    def drawROI(self):
        """Draws the ROI on the current image"""

        def roipoints(roispinboxlist):
            """Extracts indices from the spinboxes and returns them in list"""

            return [box.value() for box in roispinboxlist]

        if self.sender()==self.setRoiNcount:
            self.absImage.rois['ncount'] = roipoints(self.roiNinputs)
            self.absImage.drawROI('ncount')
        elif self.sender()==self.setRoiAnalysis:
            self.absImage.rois['analysis'] = roipoints(self.roiAnInputs)
            self.absImage.drawROI('analysis')


    def clearROI(self):
        if self.sender()==self.clearRoiNcount:
            self.absImage.clearROI('ncount')
        elif self.sender()==self.clearRoiAnalysis:
            self.absImage.clearROI('analysis')


    def setRoiCoords(self):
        """This is a bit clumsy. Ideally just drag-select. Also, check x0<x1"""
        coords = self.absImage.marker
        if coords:
            if self.sender()==self.roiAnLabels[0]:
                self.roiAnInputs[0].setValue(coords[0])
                self.roiAnInputs[2].setValue(coords[1])
            elif self.sender()==self.roiAnLabels[1]:
                self.roiAnInputs[1].setValue(coords[0])
                self.roiAnInputs[3].setValue(coords[1])
            elif self.sender()==self.roiNLabels[0]:
                self.roiNinputs[0].setValue(coords[0])
                self.roiNinputs[2].setValue(coords[1])
            elif self.sender()==self.roiNLabels[1]:
                self.roiNinputs[1].setValue(coords[0])
                self.roiNinputs[3].setValue(coords[1])


    def setImgLimits(self):
        """Update vmin and vmax of the divided image and redraw."""

        vmin, vmax = self.getImgLimits()
        self.absImage.set_viewlimits(vmin, vmax)
        self.absImage.draw()


    def getImgLimits(self):
        """Return the values for vmin and vmax for the divided image"""

        vmin = self.imgctrlbox.minCtrl.value()
        vmax = self.imgctrlbox.maxCtrl.value()

        return vmin, vmax


    def updateColormap(self, cmap):
        """"""

        self.absImage.set_colormap(str(cmap))


    def updatePixval(self, text):
        """Updates the status bar of the image with the pixel value

        **Inputs**

          * text: string, this string gets written directly into label

        """

        self.absBar.setText(text)


    def updateMarkerval(self, text):
        """Updates the marker label with the new pixel coords and value"""

        self.absMarker.setText(text)


    def updateAbsImage(self, index):
        """Called when left-clicking on a grid image, reloads raw image"""

        self.absImage.img = self.img_list[index]
        self.absImage.datafilepath = self.datafilelist[index]
        self.absImage.update_img()


    def cycleImages(self):
        """Cycle through the raw images"""

        if self.absImage.rawdata_index == self.absImage.img.shape[2]-1:
            self.absImage.rawdata_index = 0
            self.absImage.set_viewlimits(*self.getImgLimits())
        else:
            self.absImage.rawdata_index += 1
            self.absImage.set_viewlimits(None, None)
        self.setAbsLabel()
        self.absImage.update_img()


    def setAbsLabel(self):
        """Set the image label"""

        labels = ['Current image', 'Probe with atoms',
                  'Probe without atoms', 'Dark field', 'Dark field 2']
        self.absLabel.setText(labels[self.absImage.rawdata_index])


    def fitImage(self):
        """Takes care of fitting the current image and plotting the result"""

        self.fitForceButton.setText('Fitting...')

        img, roi = self.absImage.getImgROI('analysis')
        self.guifitfuncs.roi = roi
        self.guifitfuncs.current_datafilename = self.absImage.datafilepath
        self.fitobj = Fitter(img)
        self.connect(self.fitobj, SIGNAL("fitresult"), self.plotFitImage)
        self.fitobj.check_ellipse = self.ellipseCalc.isChecked()

        func_idx = self.fitFunc.currentIndex()
        self.guifitfuncs.current_func = self.guifitfuncs.funcs[func_idx]['func']
        self.fitobj.func = self.guifitfuncs.funcs[func_idx]['name']

        self.fitobj.start()


    def plotFitImage(self, fitresults):
        """Plot the result of a fit after it has finished"""

        if isinstance(fitresults, str):
            # fit failed if fitresults is a string
            self.emit(SIGNAL("updateStatusBar"), fitresults)
        else:
            self.emit(SIGNAL("updateStatusBar"), 'Fitting succeeded')
            self.guifitfuncs.current_func(self.plotFigure, fitresults)

        self.fitForceButton.setText('Fit now')


class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)

        self.lock = QReadWriteLock()


        self.cwidget = CentralWidget()
        self.setCentralWidget(self.cwidget)

        self.dirmonitor = dirmonitor.Walker(self.lock, self)
        self.connect(self.dirmonitor, SIGNAL("changed"), self.changed)

        self.connect(self.cwidget.pathButton, SIGNAL("clicked()"), self.setPath)

        # display status bar string for central widget
        self.connect(self.cwidget, SIGNAL("updateStatusBar"),
                     self.updateStatusBar)
        self.connect(self.cwidget, SIGNAL("updateProgressBar"),
                     self.updateProgressBar)
        for img in self.cwidget.gridImages:
            self.connect(img, SIGNAL("updateStatusBar"), self.updateStatusBar)
            self.connect(img, SIGNAL("displayPluginMenu"), self.displayPluginMenu)
        self.status = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setRange(0, 9)
        self.progress.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.progress.setMinimumWidth(125)
        self.status.addPermanentWidget(self.progress)
        self.status.showMessage(\
            "Click the 'Set Path' button to start monitoring")

        # populate drop down menus
        self._populate_dropdown_menus()

        # restore state from previous session
        settings = QSettings('OdysseusGUI')
        self.path = QDir.toNativeSeparators(\
            settings.value("Path", QVariant(QDir.homePath())).toString())
        self.restoreGeometry(settings.value("Geometry").toByteArray())
        self.restoreState(settings.value("MainWindow/State").toByteArray())
        # restore ROIs
        roi_inds = ['X0', 'X1', 'Y0', 'Y1']
        for num, ind in enumerate(roi_inds):
            self.cwidget.roiNinputs[num].setValue(\
                settings.value(''.join(["roiNcount/", ind])).toInt()[0])
            self.cwidget.roiAnInputs[num].setValue(\
                settings.value(''.join(["roiAnalysis/", ind])).toInt()[0])
        self.cwidget.ellipseCalc.setChecked(settings.value("EllipseCalc").toBool())
        self.cwidget.autoFit.setChecked(settings.value("AutoFit").toBool())

        # import plugin scripts
        plugindir = [os.path.join(sys.path[0], 'plugins')]
        self.plugin_manager = pluginmanager.PluginManager(directories_list=plugindir,\
                                            plugin_info_ext="odysseus-plugin")
        self.plugin_manager.collectPlugins()
        self.pluginwindowlist = []

        self.setWindowTitle("Odysseus - the cold atom viewer")


    def setPath(self):
        path = QFileDialog.getExistingDirectory(self,
                    "Choose a Path to Monitor and Display", self.path)
        if path.isEmpty():
            if self.dirmonitor.isRunning():
                self.status.showMessage("Continuing to monitor the same path,"\
                    "click the 'Set Path' button to alter path")
            else:
                self.status.showMessage(\
                    "Click the 'Set Path' button to start monitoring")
            return
        if self.dirmonitor.isRunning():
            self.dirmonitor.setWaiting(True)
        self.path = str(QDir.toNativeSeparators(path))
        self.cwidget.pathLabel.setText(self.path)
        self.status.clearMessage()

        # set log file
        self.cwidget.guifitfuncs.txtfilename = os.path.join(self.path,
                                                            'fitresults.txt')

        # load images from path into GUI
        self.cwidget.load_imgs(self.path)
        self.cwidget.display_imgs()

        # start monitoring for new images
        self.dirmonitor.setPath(self.path)
        if self.dirmonitor.isRunning():
            self.dirmonitor.setWaiting(False)
            self.status.showMessage("Monitoring resumed")
        else:
            self.dirmonitor.start()
            self.status.showMessage("Monitoring started")
        self.updateProgressBar(9)


    def changed(self, fnames):
        """Called when dir_monitor detects a change in TIF files

        fnames is a list of new files. If there is just one new file, it
        is loaded, if there is more than one all files get sorted again and
        reloaded.

        """

        try:
            self.updateProgressBar(0)
            if len(fnames)==1:
                self.cwidget.load_newimg(fnames[0])
                self.cwidget.display_imgs()
                self.status.showMessage(\
                        ''.join(['Latest image: ', str(fnames[0])]))
                self.updateProgressBar(9)
            else:
                self.cwidget.load_imgs(self.path)
                self.cwidget.display_imgs()
                self.status.showMessage('Multiple new images loaded')
                self.updateProgressBar(9)
        except IOError:
            self.status.showMessage('Can not open image, maybe a permissions problem?')


    def updateStatusBar(self, msg):
        """Displays the string msg in the status bar"""

        self.status.showMessage(msg)


    def updateProgressBar(self, val):
        """Updates the progress bar, val should be integer in range (0, 9)"""

        if not self.progress.isVisible():
            self.status.addPermanentWidget(self.progress)
            self.progress.show()
        self.progress.setValue(val)
        if val==self.progress.maximum():
            QTimer.singleShot(8000, self.hideProgressBar)


    def hideProgressBar(self):
        """Hides the progress bar, used with timer"""

        # removeWidget is a badly named method, it just hides the widget
        self.status.removeWidget(self.progress)


    def fileOpen(self):
        """Open a raw image file and display as first image"""

        fname = unicode(QFileDialog.getOpenFileName(self,
                            "Odysseus - Choose Image", self.path,
                            "Raw image files (*.TIF);;XCamera image files (*.xraw0)"))
        if fname:
            self.cwidget.load_newimg(fname)
            self.cwidget.display_imgs()


    def fileSaveas(self):
        """Save a file in a format (.h5/ .npy/ .txt) selectable by extension"""

        fname = QFileDialog.getSaveFileName(self, \
                        "Save the image data as ... (default format is .h5)",
                        getattr(self, 'savedir', self.path),
                        "All supported files (*.h5 *.npy *.txt);;HDF5 files (*.h5);;Numpy binary files (*.npy);;ASCII text files (*.txt)")
        if fname:
            name, ext = os.path.splitext(str(fname))
            self.savedir, savefile = os.path.split(name)
            if not ext:
                ext = '.h5'
            imgdata = self.cwidget.absImage.img[:, :, 0]
            fname = ''.join([name, ext])

            if ext=='.h5':
                imageio.save_hdfimage(imgdata, fname)
            elif ext=='.npy':
                np.save(fname, imgdata)
            elif ext=='.txt':
                np.savetxt(fname, imgdata, fmt='%1.4f')


    def closeEvent(self, event=None):
        self.dirmonitor.setStopped()

        settings = QSettings('OdysseusGUI')
        settings.setValue("Path", QVariant(self.path))
        settings.setValue("Geometry", QVariant(self.saveGeometry()))
        settings.setValue("MainWindow/State", QVariant(self.saveState()))
        # ROI settings
        roi_inds = ['X0', 'X1', 'Y0', 'Y1']
        for num, ind in enumerate(roi_inds):
            settings.setValue(''.join(['roiNcount/', ind]),
                              QVariant(self.cwidget.roiNinputs[num].value()))
            settings.setValue(''.join(['roiAnalysis/', ind]),
                              QVariant(self.cwidget.roiAnInputs[num].value()))

        settings.setValue("EllipseCalc",
                          QVariant(self.cwidget.ellipseCalc.isChecked()))
        settings.setValue("AutoFit", QVariant(self.cwidget.autoFit.isChecked()))


    def createAction(self, text, slot=None, shortcut=None, icon=None,
                     tip=None, checkable=False, signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action


    def addActions(self, target, actions):
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)


    def _populate_dropdown_menus(self):
        """All the dropdown menu entries for the GUI, called by __init__"""

        fileOpenAction = self.createAction("&Open...", self.fileOpen,
                                           QKeySequence.Open, "fileopen",
                                           "Open an existing image file")
        fileSaveAction = self.createAction("&Save As...", self.fileSaveas,
                                           "Ctrl+S",
                                           "Save the image as ...")
        fileQuitAction = self.createAction("&Quit", self.close,
                "Ctrl+Q", "filequit", "Close the application")

        helpAboutAction = self.createAction("&About Odysseus",
                self.helpAbout)
        openManualAction = self.createAction("User Manual", self.openManual)

        fileMenu = self.menuBar().addMenu("&File")
        helpMenu = self.menuBar().addMenu("&Help")

        self.addActions(fileMenu, (fileOpenAction, fileSaveAction,
                                   None, fileQuitAction))
        self.addActions(helpMenu, (openManualAction, None, helpAboutAction))


    def helpAbout(self):
        if platform.system()=='Windows':
            pyversion = sys.winver
        else:
            pyversion = platform.python_version()
        QMessageBox.about(self, "About Odysseus",
                """<b>Odysseus - the cold atom viewer</b> v %s
                <p>Copyright &copy; 2008 Ketterle group, MIT.
                All rights reserved.
                <p>This application can be used to view images
                obtained from cold atom experiments.
                <p>Python %s - Qt %s - PyQt %s on %s""" % (
                __version__, pyversion,
                QT_VERSION_STR, PYQT_VERSION_STR, platform.system()))


    def openManual(self):
        """Launch a browser (or a new tab) and open the user manual in it"""
        url = os.path.join(sys.path[0], 'docs', '.build', 'html', 'index.html')
        webbrowser.open_new_tab(url)


    def displayPluginMenu(self, imgnumber, imgpath):
        """Displays a menu with all available plugins."""

        # populate the context menu
        contextMenu = QMenu('Analysis Plugins', self)
        for plugin in self.plugin_manager.getPluginsOfCategory('Default'):
            # plugin is a PluginInfo object
            contextMenu.addAction(plugin.name)
        clickAction = contextMenu.exec_(QCursor.pos())

        # respond to a context menu click
        if clickAction:
            # save and reset rc params (so plugins can do whatever they want)
            currentparams = mpl.pyplot.rcParams.copy()
            mpl.pyplot.rcdefaults()

            # execute main() function of plugin
            plugin_name = clickAction.text()
            plugin = self.plugin_manager.getPluginByName(plugin_name)
            plugin.plugin_object.imgpath = imgpath
            try:
                roilist = self.cwidget.absImage.rois['analysis']
                clicked_img = self.cwidget.img_list[imgnumber][:, :, 0]
                if self.cwidget.absImage.roiboxes['analysis']:
                    roislice = (slice(roilist[2], roilist[3]),
                                slice(roilist[0], roilist[1]))
                else:
                    roislice = (slice(0, clicked_img.shape[0]),
                                slice(0, clicked_img.shape[1]))
                self.pluginwindowlist.append(plugin.plugin_object.create_window(\
                    clicked_img, roislice, plugin_name))
            except:
                popupbox = MaxsizeMessagebox.information(self, \
                                "Plugin error - %s" %(plugin_name),\
                                cgitb.html(sys.exc_info()))

            # restore rc params
            mpl.pyplot.rcParams.update(currentparams)


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("Ketterle group, MIT")
    app.setOrganizationDomain("cua.mit.edu/ketterle_group/")
    app.setApplicationName("Odysseus")
    app.setWindowIcon(QIcon(":/icon.png"))

    form = MainWindow()
    form.show()
    app.exec_()


if __name__ == '__main__':
    main()
