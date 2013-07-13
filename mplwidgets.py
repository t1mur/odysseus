import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import numpy as np
import matplotlib as mpl
from pylab import show, close
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.figure import Figure

from guihelpfuncs import coldict


# cursors
class Cursors:  #namespace
    HAND, POINTER, SELECT_REGION, MOVE = range(4)
cursors = Cursors()


class MyQTToolbar(NavigationToolbar2QT):
    """Slight modification to the standard MPL QT4 toolbal.

    toolitems is the list of buttons to add to the toolbar, the format is:
    text, tooltip_text, image_file, callback(str)

    """

    toolitems = (
        ('Home', 'Reset original view', 'home.ppm', 'home'),
        ('Back', 'Back to  previous view','back.ppm', 'back'),
        ('Forward', 'Forward to next view','forward.ppm', 'forward'),
        (None, None, None, None),
        ('Zoom', 'Zoom to rectangle','zoom_to_rect.ppm', 'zoom'),
        ('Save', 'Save the figure','filesave.ppm', 'save_figure'),
        )

    margin = 8 # extra margin for the toolbar


    def mouse_move(self, event):
        """copied from MPL backend_bases.py and modified"""
        if not event.inaxes or not self._active:
            if self._lastCursor != cursors.POINTER:
                self.set_cursor(cursors.POINTER)
                self._lastCursor = cursors.POINTER
        else:
            if self._active=='ZOOM':
                if self._lastCursor != cursors.SELECT_REGION:
                    self.set_cursor(cursors.SELECT_REGION)
                    self._lastCursor = cursors.SELECT_REGION
                if self._xypress:
                    x, y = event.x, event.y
                    lastx, lasty, a, ind, lim, trans= self._xypress[0]
                    self.draw_rubberband(event, x, y, lastx, lasty)

        if event.inaxes and event.inaxes.get_navigate():

            try:
                x = int(event.xdata)
                y = int(event.ydata)
                if isinstance(self.canvas, SingleImageCanvas):
                    dataval = self.canvas.img[y, x, self.canvas.rawdata_index]
                else:
                    dataval = 0.0
                msg = '(X; Y)=(%s; %s) ;  I=%1.2f'%(x, y, dataval)
            except ValueError: pass
            except OverflowError: pass
            else:
                if len(self.mode):
                    self.set_message('%s\n%s' %(self.mode, msg))
                else:
                    self.set_message(msg)
        else: self.set_message(self.mode)


class MyMplCanvas(FigureCanvas):
    """Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.)."""

    def __init__(self, parent=None, img=np.ones((576, 384))*1.2, \
        width=3, aspect=576/384.):
        """width is in inches"""

        height = width*aspect
        self.aspect = aspect
        self.img = img
        # imgsize is used to check if the shape has changed, see shapechange()
        self.imgsize = self.img.shape
        self.datafilepath = None

        # roi is defined as [x0, x1, y0, y1]
        self.rois = {'ncount':None, 'analysis':None}
        self.roiboxes = {'ncount':None, 'analysis':None}
        self.roicols = {'ncount':coldict['purple'], 'analysis':coldict['blue']}
        self.marker = None
        self.markerlines = None
        self.colmaps = {'gray':mpl.cm.gray, 'copper':mpl.cm.copper,
                        'hot':mpl.cm.hot, 'jet':mpl.cm.jet,
                        'spectral':mpl.cm.spectral, 'earth':mpl.cm.gist_earth}

        mpl.pyplot.rc('figure.subplot', left=1e-3)
        mpl.pyplot.rc('figure.subplot', bottom=1e-3)
        mpl.pyplot.rc('figure.subplot', right=1-1e-3)
        mpl.pyplot.rc('figure.subplot', top=1-1e-3)
        mpl.pyplot.rc('figure', fc=coldict['bgcolor'], ec=coldict['bgcolor'])
        mpl.pyplot.rc('axes', fc=coldict['bgcolor'])
        mpl.pyplot.rc('axes', lw=0.5)
        mpl.pyplot.rc('axes', labelsize=10)
        mpl.pyplot.rc('xtick', labelsize=8)
        mpl.pyplot.rc('ytick', labelsize=8)

        self.fig = Figure(figsize=(width, height))
        self.ax = self.fig.add_subplot(111)
        # We want the axes cleared every time plot() is called
        self.ax.hold(False)

        self.init_figure()
        FigureCanvas.__init__(self, self.fig)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(self, \
                QSizePolicy.Expanding, QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)
        self.setMinimumSize(200, 200)
        self.setFocusPolicy(Qt.ClickFocus)


    def sizeHint(self):
        w, h = self.get_width_height()
        return QSize(w, round(w*self.aspect))


    def heightForWidth(self, width):
        """reimplemented from QWidget to ensure we have constant aspect ratio"""

        return round(width*self.aspect)


class SingleImageCanvas(MyMplCanvas):
    """Holds a single absorption image in an MPL figure."""

    def __init__(self, parent=None, img=np.ones((576, 384, 4))*1.2, \
        width=1.5, aspect=576/384.):
        """add index for raw data frames pwa, pwoa, df."""

        self.rawdata_index = 0
        self.hsizelims = (200, 800)
        self.vsizelims = (200, 600)
        super(SingleImageCanvas, self).__init__(parent, img=img, width=width)
        self.resize(img.shape[1], img.shape[0])


    def init_figure(self, vmin=0, vmax=1.35):
        """Generate a single image object and ROIs, markers, etc"""

        rawimage = self.img[:, :, self.rawdata_index]
        if self.rawdata_index==0:
            self.imobject = self.ax.imshow(rawimage, cmap=mpl.cm.gray,
                                           vmin=vmin, vmax=vmax,
                                           interpolation='nearest')
        else:
            self.imobject = self.ax.imshow(rawimage, cmap=mpl.cm.gray,
                                           interpolation='nearest')
        self.ax.set_xticks([])
        self.ax.set_yticks([])


    def update_img(self):
        """Redraws the image, but leaves zoom, cursor etc unchanged."""

        self.imobject.set_array(self.img[:, :, self.rawdata_index])
        if not self.img.shape==self.imgsize:
            self.shapechange()
        self.fig.canvas.draw()


    def set_viewlimits(self, vmin, vmax):
        """"""

        norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
        self.imobject.set_norm(norm)


    def set_colormap(self, cmap='gray'):
        """Set the colormap of the image and draw it."""

        self.imobject.set_cmap(self.colmaps[cmap])
        self.figure.canvas.draw()


    def shapechange(self):
        """If the image has a different shape, update the widget geometry"""

        self.imgsize = self.img.shape
        imsize = self.imgsize

        def check_sizelims(vhsize, sizelims):
            """vhsize is the current size of the dimension to check, sizelims
            a two-element tuple (min,max). Return True if imsize is within
            lims, False otherwise.
            """
            if vhsize < sizelims[0] or vhsize > sizelims[1]:
                return False
            else:
                return True

        def find_scalefactor(vhsize, sizelims):
            """Return scale factor needed to get the size within given limits"""
            if vhsize < sizelims[0]:
                scale = np.ceil(sizelims[0] / float(vhsize))
            elif vhsize > sizelims[1]:
                scale = 1. / np.ceil(float(vhsize) / sizelims[1])
            else:
                scale = 1
            return scale


        hscale = find_scalefactor(imsize[1], self.hsizelims)
        if check_sizelims(imsize[0]*hscale, self.vsizelims):
            hsize = round(imsize[1] * hscale)
            vsize = round(imsize[0] * hscale)
        else:
            vscale = find_scalefactor(imsize[0], self.vsizelims)
            if check_sizelims(imsize[1]*vscale, self.hsizelims):
                hsize = round(imsize[1] * vscale)
                vsize = round(imsize[0] * vscale)
            else:
                # no common scale factor works, scale each dimension separately
                hsize = round(imsize[1] * hscale)
                vsize = round(imsize[0] * vscale)

        self.aspect = float(vsize) / hsize
        self.resize(hsize, vsize)
        self.updateGeometry()
        self.emit(SIGNAL("SizeChange"))

        # now do all the redrawing (we do not draw ROIs and marker)
        for key in self.rois.keys():
            self.clearROI(key)
            self.clearMarker()
        self.init_figure()


    def mousePressEvent(self, event):
        """Left-click is handled by MPL, right-click not."""

        x = event.pos().x()
        # flipy so y=0 is bottom of canvas
        y = self.figure.bbox.height - event.pos().y()

        if event.button()==1:
            button = self.buttond[event.button()]
            FigureCanvasBase.button_press_event( self, x, y, button )
        else:
            if event.button()==2:
                try:
                    xdata, ydata = self.ax.transData.inverted().\
                         transform_point((x, y))
                except ValueError:
                    xdata  = None
                    ydata  = None
                self.marker = [int(xdata), int(ydata)]
                self.drawMarker()


    def drawROI(self, roi_id):
        """roi_id is a string, specifying the key for the rois dictionaries"""

        if self.rois[roi_id]:
            if self.roiboxes[roi_id]:
                self.roiboxes[roi_id].remove()
            roi = self.rois[roi_id]
            poly = mpl.patches.Polygon(((roi[0], roi[2]),
                                        (roi[1], roi[2]),
                                        (roi[1], roi[3]),
                                        (roi[0], roi[3])),
                                       ec=self.roicols[roi_id], fc='none',
                                       lw=0.5)
            self.ax.add_patch(poly)
            self.roiboxes[roi_id] = poly

            self.fig.canvas.draw()


    def clearROI(self, roi_id):
        """roi_id is a string, specifying the key for the rois dictionaries"""

        if self.rois[roi_id]:
            if self.roiboxes[roi_id]:
                self.roiboxes[roi_id].remove()
                self.roiboxes[roi_id] = None

                self.fig.canvas.draw()


    def drawMarker(self, col=coldict['lightblue']):
        """Draws a cross at the point where the user left-clicked"""

        if self.marker:
            xx, yy = self.marker

            if self.markerlines:
                marker_hline, marker_vline = self.markerlines
                hpoints = marker_hline.get_ydata().size
                marker_hline.set_ydata(np.ones(hpoints)*yy)
                vpoints = marker_hline.get_xdata().size
                marker_vline.set_xdata(np.ones(vpoints)*xx)
            else:
                self.ax.hold(True)
                marker_hline = self.ax.axhline(yy, color=col)
                marker_vline = self.ax.axvline(xx, color=col)
                self.ax.hold(False)
                self.markerlines = [marker_hline, marker_vline]

            self.fig.canvas.draw()

            msg = '(X, Y)=(%s, %s) ;  I=%1.2f'\
                %(xx, yy, self.img[yy, xx, self.rawdata_index])
            self.emit(SIGNAL("MarkerPixval"), msg)


    def clearMarker(self):
        """Clears the marker and marker label"""

        self.marker = None
        if self.markerlines:
            for line in self.markerlines:
                line.remove()
            self.markerlines = None

        self.fig.canvas.draw()
        self.emit(SIGNAL("MarkerPixval"), "")


    def keyPressEvent(self, event):
        """Move marker with arrows on the keyboard"""

        if self.marker:
            if event.matches(QKeySequence.MoveToNextChar):
                try:
                    if self.marker[0] < self.img.shape[1] - 1:
                        self.marker[0] += 1
                        self.drawMarker()
                except IndexError:
                    pass
            elif event.matches(QKeySequence.MoveToPreviousChar):
                try:
                    if self.marker[0] > 0:
                        self.marker[0] -= 1
                        self.drawMarker()
                except IndexError:
                    pass
            elif event.matches(QKeySequence.MoveToNextLine):
                try:
                    if self.marker[1] < self.img.shape[0] - 1:
                        self.marker[1] += 1
                        self.drawMarker()
                except IndexError:
                    pass
            elif event.matches(QKeySequence.MoveToPreviousLine):
                try:
                    if self.marker[1] > 0:
                        self.marker[1] -= 1
                        self.drawMarker()
                except IndexError:
                    pass
            else:
                event.ignore()
        else:
            event.ignore()


    def getImgROI(self, roi_id='analysis'):
        """Returns the image data within the ROI as a 2D array

        roiname is string with value 'ncount' or 'analysis'

        """

        roi = self.rois[roi_id]
        if roi:
            # roi is [x0, x1, y0, y1], where x is the second index of img
            imgroi = self.img[roi[2]:roi[3], roi[0]:roi[1], 0]
        else:
            imgroi = self.img[:, :, 0]

        return imgroi, roi


class InfoPlotCanvas(MyMplCanvas):
    """Displays the results of the image fitting"""

    def __init__(self, parent=None, figsize=(6,4), dpi=100):
        """figsize is in inches"""

        mpl.pyplot.rc('figure.subplot', left=0.15)
        mpl.pyplot.rc('figure.subplot', bottom=0.15)
        mpl.pyplot.rc('figure.subplot', right=0.95)
        mpl.pyplot.rc('figure.subplot', top=0.95)

        self.fig = Figure(figsize=figsize, dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        # We want the axes cleared every time plot() is called
        self.ax.hold(False)
        self.compute_figure()

        FigureCanvas.__init__(self, self.fig)
        self.setParent(parent)
        FigureCanvas.setSizePolicy(self, \
                    QSizePolicy.Preferred, QSizePolicy.Preferred)
        FigureCanvas.updateGeometry(self)
        self.setMinimumSize(150, 100)
        self.setMaximumSize(400, 266)


    def sizeHint(self):
        w, h = self.get_width_height()
        return QSize(w, h)


    def compute_figure(self):
        """Plot the fit"""

        self.ax.set_xlabel(r'$r$ [pix]')
        self.ax.set_ylabel(r'$OD$')


class PngWidget(QWidget):
    """The widget for the image history"""

    def __init__(self, pngimg, datapath, ncount, gridindex=0, parent=None):
        """pngimg is the full path to the .png file, datapath to the raw data"""
        super(PngWidget, self).__init__(parent)

        self.imgpath = pngimg
        self.datapath = datapath
        self.index = int(gridindex)
        self.img = QLabel()
        self.img.setPixmap(QPixmap(pngimg))
        self.ncount = QLabel()
        if ncount:
            self.ncount.setText('N = %1.1fk'%(ncount*1e-3))
        else:
            self.ncount.clear()

        self.ncount.setFrameStyle(QFrame.StyledPanel)
        pngbox = QVBoxLayout()
        pngbox.addStretch()
        pngbox.addWidget(self.img)
        pngbox.addWidget(self.ncount)
        self.setLayout(pngbox)


    def update(self, pngimg, datapath, ncount):
        self.imgpath = pngimg
        self.datapath = datapath
        if pngimg:
            imgname = os.path.split(pngimg)[1][:-4]
            self.img.setToolTip(imgname)
            self.img.setPixmap(QPixmap(pngimg))
            self.ncount.setText('N = %1.1fk'%(ncount*1e-3))


    def mousePressEvent(self,event):
        """Left-click loads image in rawImage, right-click does plugins"""

        pngdir, imgname = os.path.split(self.imgpath)
        # catch left click on non-blank images
        if event.button()==1 and not imgname=='blankimg.png':
            self.emit(SIGNAL("updateAbsImage"), self.index)

        # catch right click on non-blank images
        if event.button()==2 and not imgname=='blankimg.png':
            # construct path to tiff image
            tiffname = imgname.replace('.png', '.TIF')
            tiffdir = os.path.split(pngdir)[0]
            tiffpath = os.path.join(tiffdir, tiffname)
            #display menu
            self.emit(SIGNAL("displayPluginMenu"), self.index, tiffpath)


def save_png(img, path, fname, hsize=1.5, vmin=0., vmax=1.35):
    """Save an image as a png file

    **Inputs**

      * img: 2D array, usually the transmission image
      * path: str, the directory above the one where the png image will be saved
      * fname: str, the desired filename, with or without extension

    **Outputs**

      * pngpath: str, the complete path to the generated png file

    """

    path = str(path)
    fname = str(fname)
    pngdir = os.path.join(path, 'png')
    try:
        os.mkdir(pngdir)
    except OSError:
        # if png directory already exists, do nothing
        pass

    aspect = float(img.shape[0])/img.shape[1]
    mpl.pyplot.rc('figure.subplot', left=1e-3)
    mpl.pyplot.rc('figure.subplot', bottom=1e-3)
    mpl.pyplot.rc('figure.subplot', right=1-1e-3)
    mpl.pyplot.rc('figure.subplot', top=1-1e-3)

    fig = Figure(figsize=(hsize, hsize*aspect))
    canvas = FigureCanvas(fig)

    ax = fig.add_subplot(111)
    ax.imshow(img, cmap=mpl.cm.gray, vmin=vmin, vmax=vmax)
    ax.set_xticks([])
    ax.set_yticks([])

    fname = os.path.splitext(fname)[0] + '.png'
    pngpath = os.path.join(pngdir, fname)
    fig.savefig(pngpath)
    close(fig)

    return pngpath


class BlankCanvas(FigureCanvas):
    """Initialize a blank image, to be used in popup plugins etc.

    Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.).

    """

    def __init__(self, parent=None):
        """width is in inches"""

        self.fig = Figure(figsize=(6, 4))
        self.ax = self.fig.add_subplot(111)

        FigureCanvas.__init__(self, self.fig)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(self, \
                QSizePolicy.Expanding, QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)


class BlankCanvasWithToolbar(FigureCanvas):
    """Initialize a blank image, to be used in popup plugins etc.

    Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.).

    """

    def __init__(self, parent=None):
        """width is in inches"""

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)

        FigureCanvas.__init__(self, self.fig)
        self.setParent(parent)