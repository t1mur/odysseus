import os

import texreport
from imageio import *
from imageprocess import *


dirname = 'datafiles'
tifname = 'raw9.11.2008 7;35;23 PM.TIF'
imgname = os.path.join(dirname, tifname)

rawframes = import_rawframes(imgname)
transimg, odimg = calc_absimage(rawframes)
# set the ROI
transimg = transimg[120:350, 50:275]

texreport.generate_report(rawframes, transimg, imgname)
