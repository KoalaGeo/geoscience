# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DrillManager
                              -------------------
        begin                : 2018-04-13
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Roland Hill / MMG
        email                : roland.hill@mmg.com
 ***************************************************************************/
"""
from PyQt5.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QVariant
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QDialog, QProgressBar, QProgressDialog, qApp

from qgis.core import *
from qgis.utils import *
from qgis.gui import *
import numpy as np

from .quaternion import Quaternion

# Initialize Qt resources from file resources.py
from .resources import *
from .drillsetup_dialog import DrillSetupDialog
from .drilltrace_dialog import DrillTraceDialog

import os.path
import math
import platform

class Collar:
    id = ''
    east = 0.0
    north = 0.0
    elev = 0.0
    depth = 0.0
    az = 0.0
    dip = 0.0

class Survey:
    id = ''
    depth = 0.0
    az = 0.0
    dip = 0.0
    
class Surveys:
    depth = 0.0
    az = 0.0
    dip = 0.0
    
def getLayerByName(name):
    layer=None
    layerList = QgsProject.instance().mapLayersByName(name)
    if len(layerList) > 0:
        layer = layerList[0]

    return layer

def getFieldByName(layer, name):
    field = QgsField()
    if layer is not None and layer.isValid() and name != "None":
        dp = layer.dataProvider()
        index = dp.fieldNameIndex(name)
        if index > -1:
            field = dp.field(index)
    return field

# Retrieve the name of the layer from the QGIS project file with the supplied entry label
def readProjectLayer(entry):
    name, ok = QgsProject.instance().readEntry ("Geoscience", entry)
    if ok and name != "None":
        layer = getLayerByName(name)
        if layer != None:
            return layer
        else:
            return None
    else:
        return None

# Write the supplied layer name into the QGIS project file next to the supplied entry label
def writeProjectLayer(entry, layer):
    if layer is not None:
        try:
            QgsProject.instance().writeEntry("Geoscience", entry, layer.name())
        except:
            QgsProject.instance().writeEntry("Geoscience", entry, "None")
    else:
        QgsProject.instance().writeEntry("Geoscience", entry, "None")
        
# Retrieve the name of the field from the QGIS project file with the supplied entry label
def readProjectField(entry):
    name, ok = QgsProject.instance().readEntry ("Geoscience", entry)
    return name

# Write the supplied field name into the QGIS project file next to the supplied entry label
def writeProjectField(entry, field):
    QgsProject.instance().writeEntry("Geoscience", entry, field)
        
# Retrieve a number from the QGIS project file with the supplied entry label
def readProjectNum(entry, default):
    val, ok = QgsProject.instance().readNumEntry ("Geoscience", entry)
    if ok:
        return val
    else:
        return default
    
# Retrieve a bool from the QGIS project file with the supplied entry label
def readProjectBool(entry, default):
    val, ok = QgsProject.instance().readBoolEntry ("Geoscience", entry)
    if ok:
        return val
    else:
        return default

# Write the supplied value (number or bool) into the QGIS project file next to the supplied entry label
def writeProjectData(entry, val):
    QgsProject.instance().writeEntry("Geoscience", entry, val)

# Calculate an interpolated 3D point at given depth from the supplied polyline.
# The polyline must have constant segment lengths given by segLength
def interpPolyline(depth, segLength, polyline):
    p = QgsPoint()
    i = depth / segLength
    i0 = int(i)
    ratio = i - i0

    p0 = polyline[i0]
    if ratio > 0.0:
        p1 = polyline[i0 + 1]
        dp = (p1 - p0) * ratio
        p = p0 + dp
    else:
        p = p0
    return p, i

# Process the url to provide a valid filename
def uriToFile(url):
    fileName = url
    if fileName.startswith("file:///"):
        if platform.system() == 'Windows':
            fileName = fileName[8:]
        elif platform.system() == 'Linux':
            fileName = fileName[7:]
    fileName = fileName.replace("%20", " ")
    fileName = os.path.normpath(fileName)
    return fileName
    
# The DrillManager class controls all drill related data and methods 
class DrillManager:
    def __init__(self):
        # Project data is normally read in response to a readProject signal.
        # We also do it here for when the plugin is loaded other than at startup
        self.readProjectData()

        # Create a log file        
        self.openLogFile()

    # Open a log file in the Collar Layer's directory
    def openLogFile(self):
        # Maintain a log file in case of data errors
        if self.collarLayer and self.collarLayer.isValid():
            fileName = uriToFile(self.collarLayer.dataProvider().dataSourceUri())
#            fileName = Path(fileName)
            self.logFile = open(os.path.join(os.path.dirname(fileName), "Geoscience_DrillManager_log.txt"),'w')
            if not self.logFile:
                self.logFile = open(os.path.join(os.path.expanduser("~"), "Geoscience_DrillManager_log.txt"),'w')
            self.logFile.write("Geoscience - DrillManager log file\n")
            self.logFile.write("  Note: This file is overwritten each time you run Geoscience.\n")
            self.logFile.write("  Make a copy if you want to keep the results.\n")
            # We flush the buffers in case the plugin crashes without writing the message to the file
            self.logFile.flush()

    # Setup and run the Drill Setup dialog        
    def onDrillSetup(self):
        dlg = DrillSetupDialog(self)
        dlg.show()
        result = dlg.exec_()
        # If OK button clicked then retrieve and update values
        if result:
            self.downDipNegative = dlg.checkDownDipNegative.isChecked()
            self.desurveyLength = dlg.sbDesurveyLength.value()
            self.defaultSectionWidth = dlg.teDefaultSectionWidth.text()
            self.defaultSectionStep = dlg.teDefaultSectionStep.text()
            self.collarLayer = dlg.lbCollarLayer.currentLayer()
            self.surveyLayer = dlg.lbSurveyLayer.currentLayer()
            self.collarId = dlg.fbCollarId.currentField()
            self.collarDepth = dlg.fbCollarDepth.currentField()
            self.collarEast = dlg.fbCollarEast.currentField()
            self.collarNorth = dlg.fbCollarNorth.currentField()
            self.collarElev = dlg.fbCollarElev.currentField()
            self.collarAz = dlg.fbCollarAz.currentField()
            self.collarDip = dlg.fbCollarDip.currentField()
            self.surveyId = dlg.fbSurveyId.currentField()
            self.surveyDepth = dlg.fbSurveyDepth.currentField()
            self.surveyAz = dlg.fbSurveyAz.currentField()
            self.surveyDip = dlg.fbSurveyDip.currentField()

            # Save updated values to QGIS project file            
            self.writeProjectData()
            
            # The collar layer might have changed, so re-open log file
            self.openLogFile()
        dlg.close()


    # Setup and run the Drill Trace dialog
    def onDrillDisplayTraces(self):
        dlg = DrillTraceDialog(self)
        dlg.show()
        result = dlg.exec_()
        if result:
            self.dataLayer = dlg.lbDataLayer.currentLayer()
            self.dataId = dlg.fbDataId.currentField()
            self.dataFrom = dlg.fbDataFrom.currentField()
            self.dataTo = dlg.fbDataTo.currentField()
            self.dataSuffix = dlg.teSuffix.text()
            # Save the name of each checked attribute field in a list
            self.dataFields = []
            for index in range(dlg.listFields.count()):
                if dlg.listFields.item(index).checkState():
                    self.dataFields.append(dlg.listFields.item(index).text())
                    
            self.writeProjectData()

        dlg.close()

        if result:
            # Create the down hole traces        
            self.createDownholeTrace()

    # Desurvey the data        
    def onDesurveyData(self):
        self.desurveyData()

    # Create a section
    def onDrillCreateSection(self):
        pass

    # Create the down hole traces    
    def createDownholeTrace(self):
        self.logFile.write("\nCreating Trace Layer.\n")
        self.logFile.flush()
        
        # Check that desurvey layer is available
        if not self.traceLayer.isValid() or not self.dataLayer.isValid():
            return
        
        # Set up a progress display
        pd = QProgressDialog()
        pd.setAutoReset(False)
        pd.setWindowTitle("Build Trace Layer")
        pd.setMinimumWidth(500)
        pd.setMinimum(0)
        pd.setMaximum(self.dataLayer.featureCount())
        pd.setValue(0)

        # Create memory layer
        layer = self.createDownholeLayer()

        # Get the fields from the data layer
        dp = self.dataLayer.dataProvider()
        idxId = dp.fieldNameIndex(self.dataId)
        idxFrom = dp.fieldNameIndex(self.dataFrom)
        idxTo = dp.fieldNameIndex(self.dataTo)
        # Create a list of attribute indices from the desired attribute field names
        idxAttList = []
        for name in self.dataFields:
            idx = dp.fieldNameIndex(name)
            idxAttList.append(idx)
        
        # Get the fields from the desurveyed trace layer
        tdp = self.traceLayer.dataProvider()
        idxTraceId = tdp.fieldNameIndex("CollarID")
        idxTraceSegLength = tdp.fieldNameIndex("SegLength")

        # Store the relevant desurveyed drill trace so that it's persistent between loops
        # This way we should be able to re-use it instead of re-fetching it.
        traceFeature = QgsFeature()
        currentTraceCollar = ""
        currentTraceSegLength = 1.0
        currentTracePolyline = None
        
    #Loop through downhole layer features
        # Calculate an optimum update interval for the progress bar (updating gui items is expensive)
        updateInt = max(100, long(self.dataLayer.featureCount()/100))
        for index, df in enumerate(self.dataLayer.getFeatures()):
            # Update the Progress bar
            if index%updateInt == 0:
                pd.setValue(index)
                qApp.processEvents()
            
            # Variable to hold a feature
            feature = QgsFeature()

            # get the feature's attributes
            attrs = df.attributes()
            # Check all the data is valid
            dataId = attrs[idxId]
            dataFrom = attrs[idxFrom]
            dataTo = attrs[idxTo]
            if (dataId==NULL) or (dataFrom==NULL) or (dataTo==NULL):
                continue
            dataId = dataId.strip()
            
            # Get the desurvey drill trace relevant to this collar, checking first that we don't already have it
            if not currentTraceCollar == dataId:
                # Get the correct trace feature via a query
                query = '''"CollarID" = '%s' ''' % (dataId)
                selection = self.traceLayer.getFeatures(QgsFeatureRequest().setFilterExpression(query))
                # We have a selection of features
                if selection.isValid():
                    # There should be just 1, so get the first feature
                    selection.nextFeature(traceFeature)
                    # Is the feature valid?
                    if traceFeature.isValid():
                        # Update information for the current feature
                        currentTraceCollar = dataId
                        currentTraceSegLength = traceFeature.attributes()[idxTraceSegLength]
                        # The normal asPolyline() function only returns QgsPointXY, yet we need the Z coordinate as well
                        # We therefore get a vertex iterator for the abstractGeometry and build our own list
                        currentTracePolyline = []
                        vi = traceFeature.geometry().vertices()
                        while vi.hasNext():
                            currentTracePolyline.append(vi.next())
                    else:
                        continue
                else:
                    continue
                
            # Create line representing the downhole value using From and To
            pointList = []
            # Calculate indices spanning the from and to depths, then linearly interpolate a position
            try:
                pFrom, iFrom = interpPolyline(dataFrom, currentTraceSegLength, currentTracePolyline)
            except:
                self.logFile.write("Error interpolating from polyline for hole: %s From: %f in row: %d.\n" % (dataId, dataFrom, index))
                continue

            try:
                pTo, iTo = interpPolyline(dataTo, currentTraceSegLength, currentTracePolyline)
            except:
                self.logFile.write("Error interpolating from polyline for hole: %s To: %f in row: %d.\n" % (dataId, dataTo, index))
                continue

            # Add the first (From) point to the list
            pointList.append(pFrom)
            # Add all the intermediate points (so a long interval accurately reflects the bend of the hole)
            for i in range(math.ceil(iFrom), math.floor(iTo)):
                pointList.append(currentTracePolyline[i])
            # Add the last (To) point
            pointList.append(pTo)
            
            # Set the geometry for the new downhole feature
            feature.setGeometry(QgsGeometry.fromPolyline(pointList))

            # Create a list of the attributes to be included in new file
            # These are just copied from the original down hole layer
            # according to whether the user selected the check boxes
            attList = []
            for idx in idxAttList:
                attList.append(attrs[idx])

            # Also append the 3D desurveyed From and To points
            attList.append(pointList[0].x())
            attList.append(pointList[0].y())
            attList.append(pointList[0].z())
            attList.append(pointList[1].x())
            attList.append(pointList[1].y())
            attList.append(pointList[1].z())

            # Set the attributes for the new feature
            feature.setAttributes(attList)

            # Add the new feature to the new Trace_ layer
            layer.startEditing()
            layer.addFeature(feature)
            layer.commitChanges()

        # Flush the log file in case anything was written
        self.logFile.flush()
        
        # Build the new filename for saving to disk. We are using GeoPackages
        base, ext = os.path.splitext(self.traceLayer.dataProvider().dataSourceUri())
        fileName = uriToFile(base + "_%s" % (self.dataSuffix))

        # Generate a layer label
        label = os.path.splitext(os.path.basename(fileName))[0]

        # Remove trace layer from project if it already exists
        oldLayer = getLayerByName(label)
        QgsProject.instance().removeMapLayer(oldLayer)

        #Save memory layer to Geopackage file
        error = QgsVectorFileWriter.writeAsVectorFormat(layer, fileName, "CP1250", self.traceLayer.sourceCrs(), layerOptions=['OVERWRITE=YES'])
            
        # Load the one we just saved and add it to the map
        layer = QgsVectorLayer(fileName+".gpkg", label)
        QgsProject.instance().addMapLayer(layer)
        
    def desurveyData(self):
        # Write to the log file
        self.logFile.write("\nDesurveying data.\n")
        self.logFile.flush()
        
        # Set up a progress bar
        pd = QProgressDialog()
        pd.setAutoReset(False)
        pd.setMinimumWidth(500)
        pd.setMinimum(0)
        
        # Get the relevant attribute indices
        dp = self.collarLayer.dataProvider()
        idxCollarId = dp.fieldNameIndex(self.collarId)
        idxCollarEast = dp.fieldNameIndex(self.collarEast)
        idxCollarNorth = dp.fieldNameIndex(self.collarNorth)
        idxCollarElev = dp.fieldNameIndex(self.collarElev)
        idxCollarDepth = dp.fieldNameIndex(self.collarDepth)
        idxCollarAz = dp.fieldNameIndex(self.collarAz)
        idxCollarDip = dp.fieldNameIndex(self.collarDip)

        # Are we using azimuths and dips from the collar file?
        useCollarAzDip = (idxCollarAz > -1) and (idxCollarDip > -1)
        
        # Build Collar array (Id, east, north, elev, eoh, az, dip)
        numCollars = self.collarLayer.featureCount()
        arrCollar = []

        # Update the progress bar
        pd.setWindowTitle("Build Collar Array")
        pd.setMaximum(numCollars)
        pd.setValue(0)
        
        # Loop through the collar layer and build list of collars
        for index, feature in enumerate(self.collarLayer.getFeatures()):
            # Update progress bar
            pd.setValue(index)
            
            # get the feature's attributes
            attrs = feature.attributes()
            c = Collar()
            # Check all the data is valid
            c.id = attrs[idxCollarId]
            c.east = attrs[idxCollarEast]
            c.north = attrs[idxCollarNorth]
            c.elev = attrs[idxCollarElev]
            c.depth = attrs[idxCollarDepth]
            if (c.id==NULL) or (c.east==NULL) or (c.north==NULL) or (c.elev==NULL) or (c.depth==NULL):
                continue
            c.id = c.id.strip()
            if useCollarAzDip:
                c.az = attrs[idxCollarAz]
                if c.az==NULL:
                    c.az = 0.0
                c.dip = attrs[idxCollarDip]
                if c.dip==NULL:
                    c.dip = -90 if self.downDipNegative else 90
            arrCollar.append(c)
            
        # Build Survey array (Id, depth, az, dip)
        arrSurvey = []
        if self.surveyLayer is not None and self.surveyLayer.isValid():
            numSurveys = self.surveyLayer.featureCount()
    
            # Get the attribute indices
            dp = self.surveyLayer.dataProvider()
            idxSurveyId = dp.fieldNameIndex(self.surveyId)
            idxSurveyDepth = dp.fieldNameIndex(self.surveyDepth)
            idxSurveyAz = dp.fieldNameIndex(self.surveyAz)
            idxSurveyDip = dp.fieldNameIndex(self.surveyDip)
            
            # Update progress bar
            pd.setWindowTitle("Build Survey Array")
            pd.setMaximum(numSurveys)
            pd.setValue(0)
            #Loop through Survey layer and buils list of surveys
            for index, feature in enumerate(self.surveyLayer.getFeatures()):
                pd.setValue(index)
                
                # get the feature's attributes
                attrs = feature.attributes()
                s = Survey()
                s.id = attrs[idxSurveyId]
                s.depth = attrs[idxSurveyDepth]
                s.az = attrs[idxSurveyAz]
                s.dip = attrs[idxSurveyDip]
                if (s.id==NULL) or (s.depth==NULL) or (s.az==NULL) or (s.dip==NULL):
                    continue
                s.id = s.id.strip()
                arrSurvey.append(s)
            
        # Create new layer for the desurveyed 3D coordinates. PolyLine, 1 row per collar, 2 attribute (Id, Segment Length)
        self.createDesurveyLayer()
        
        #Loop through collar list and desurvey each one
        # Update Progress bar
        pd.setWindowTitle("Desurvey Progress")
        pd.setMaximum(len(arrCollar))
        pd.setValue(0)
        #Calculate optimum update interval
        updateInt = max(100, int(len(arrCollar)/100))
        
        # Enter collar loop
        for index, collar in enumerate(arrCollar):
            pd.setValue(index)
            # Force update the progress bar visualisation every 1% as it normally only happens in idle time
            if index%updateInt == 0:
                qApp.processEvents()

            # Check the id exists                
            if not collar.id:
                continue
            
            #Build array of surveys for this collar, including the top az and dip in collar layer. Repeat last survey at EOH.
            surveys = []

            if len(arrSurvey) > 0:
                # Harvest surveys for this collar from Survey layer list
                for survey in arrSurvey:
                    if survey.id == collar.id:
                        s = Surveys()
                        s.depth = survey.depth
                        s.az = survey.az
                        s.dip = survey.dip
                        surveys.append(s)

            # If the az and dip from the collar are to be used, then insert them at depth 0.0
            # We only do this if there are no surveys from the Survey layer
            if len(surveys) == 0 and useCollarAzDip:
                s = Surveys()
                s.depth = 0.0
                s.az = collar.az
                s.dip = collar.dip
                surveys.append(s)
            
            # If there are no surveys, then the assume hole is vertical
            if len(surveys) == 0:
                s = Surveys()
                s.depth = 0.0
                s.az = 0.0
                s.dip = -90 if self.downDipNegative else 90
                surveys.append(s)
                
            # Is the hole straight? If so, we can take short cuts
            holeStraight = False
            if len(surveys) == 1:
                holeStraight = True

            # We only replicate survey to the beginning and end if the hole is not straight
            if not holeStraight:
                # Sort the surveys array by depth
                surveys.sort(key = lambda x: x.depth)                        
            
                # If surveys exist, but there isn't one at 0.0, then replicate first survey at 0.0
                if not surveys[0].depth == 0.0:
                    s = Surveys()
                    surveys.insert(0, s)
                    s.depth = 0.0
                    surveys[0].az = surveys[1].az
                    surveys[0].dip = surveys[1].dip
                    
                # If the last survey isn't at the end of hole, then repeat the last one at eoh
                if len(surveys) > 0 and surveys[-1].depth < collar.depth:
                    s = Surveys()
                    s.depth = collar.depth
                    s.az = surveys[-1].az
                    s.dip = surveys[-1].dip
                    surveys.append(s)
                
            # Create a quaternion for each survey
            quat = []
            for j, s in enumerate(surveys):
                # Rotate about positive X axis by dip degrees (depends on downDipNegative flag)
                qdip = Quaternion(axis=[1, 0, 0], degrees=(s.dip  if self.downDipNegative else -s.dip))

                # Rotate about positive Z axis by -Az degrees                        
                qaz = Quaternion(axis=[0, 0, 1], degrees=-s.az)
                
                # Combine the dip and azimuth (order is important!)
                q = qaz * qdip
                
                #Ensure the quaternion rotates the shortest way around. This can go wrong when we cross 0/360 deg.
                # If the dot product of the quats is negative then it's the wrong way,
                # so we negate the quat.
                # But, don't do it on the first one
                if j > 0:
                    if np.dot(quat[j-1].elements, q.elements) < 0.0:
                        q = -q
                quat.append(q)
                
            #Build drill trace every desurveyLength to EOH
            xs = []
            if not holeStraight:
                sz = int(collar.depth / self.desurveyLength) + 1
                depth = 0.0
                for d in range(0, sz):
                    xs.append(depth)
                    depth += self.desurveyLength
                if xs[-1] > collar.depth:
                    xs[-1] = collar.depth
                if xs[-1] < collar.depth:
                    xs.append(collar.depth)
            else:
                xs.append(0.0)
                
            # Create linestring to record the desurveyed points every Segment Length
            # This can then be used to interpolate intervening points
            feature = QgsFeature()
            # We'll create a pointlist to hold all the 3D points
            pointList = []
            # We start by adding the collar coordinates
            pointList.append(QgsPoint(collar.east, collar.north, collar.elev))
            # It's easier with a straight hole
            if not holeStraight:
                # We're going to keep iterating through the survey list looking for the bracketing surveys.
                # We therefore record the start point of the iteration as it will only go up. Saves time.
                idx0 = 0
                # We already added the location at point0 (the collar) so start from 1
                for i in range(1, len(xs)):
                    q = Quaternion()
                    # Find the lowest survey equal or less than xs
                    for j in range(idx0, len(surveys)):
                        # Is there a survey exactly at this point?
                        if surveys[j].depth == xs[i]:
                            # Update the iteration start point
                            idx0 = j
                            q = quat[j]
                            break
                        # Are there surveys bracketing this depth? If so, interpolate point
                        if surveys[j].depth < xs[i] and surveys[j+1].depth >= xs[i]:
                            # Update the iteration start point
                            idx0 = j
                            # How far are we between bracketing surveys?
                            ratio = (xs[i] - surveys[j].depth) / (surveys[j+1].depth - surveys[j].depth)
                            # Interpolate between bracketing survey rotations
                            q = Quaternion.slerp(quat[j], quat[j+1], ratio)
                            break

                    # Calculate the deviation of this segment of the hole
                    offset = q.rotate(np.array([0.0, 1.0, 0.0])) * self.desurveyLength
                    # Calculate the new point by adding the offset to the old point
                    p0 = pointList[i-1]
                    pointList.append(QgsPoint(p0.x() + offset[0], p0.y() + offset[1], p0.z() + offset[2]))
            else:
                # Calculate the offset of the bottom of hole from the top of hole in a single segment
                offset = quat[0].rotate(np.array([0.0, 1.0, 0.0])) * collar.depth
                # Add the offset to the collar
                p0 = pointList[0]
                pointList.append(QgsPoint(p0.x() + offset[0], p0.y() + offset[1], p0.z() + offset[2]))
                
            # Create new geometry (Polyline) for the feature
            feature.setGeometry(QgsGeometry.fromPolyline(pointList))
            # Add in the field attributes
            feature.setAttributes([collar.id, collar.depth if holeStraight else self.desurveyLength])
            
            # Add the feature to the layer
            self.traceLayer.startEditing()
            self.traceLayer.addFeature(feature)
            self.traceLayer.commitChanges()

        fileName = self.createTraceFilename()

        # Calculate the filename for the on disk file
        path="%s.gpkg" % (fileName)
        
        # work out a label for the layer from the file name
        label = os.path.splitext(os.path.basename(fileName))[0]
        
        # Remove trace layer from project if it already exists
        layer = getLayerByName(label)
        QgsProject.instance().removeMapLayer(layer)
        
        #Save memory layer to GeoPackage
        error = QgsVectorFileWriter.writeAsVectorFormat(self.traceLayer, fileName, "CP1250", self.collarLayer.sourceCrs(), layerOptions=['OVERWRITE=YES'])

        # Load the layer we just saved so the user can manipulate a real layer
        self.traceLayer = QgsVectorLayer(path, label)
        QgsProject.instance().addMapLayer(self.traceLayer)

    def createTraceFilename(self):
        # Build the new filename
        base, ext = os.path.splitext(self.collarLayer.dataProvider().dataSourceUri())
        fileName = uriToFile(base + "_Trace")
        return fileName
    
    def createDesurveyLayer(self):
        #Find CRS of collar layer
        crs = self.collarLayer.sourceCrs()
        
        #Create a new memory layer
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "gt_Trace", "memory")
        layer.setCrs(crs)
        dp = layer.dataProvider()
        dp.addAttributes([
            QgsField("CollarID",  QVariant.String, "string", 16),
            QgsField("SegLength",  QVariant.Double, "double", 5, 2)
            ])
        layer.updateFields() # tell the vector layer to fetch changes from the provider
        self.traceLayer = layer
    
    def createDownholeLayer(self):
        #Create a new memory layer
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "gt_Trace", "memory")
        layer.setCrs(self.traceLayer.sourceCrs())
        atts = []
        # Loop through the list of desired field names that the user checked
        for field in self.dataLayer.fields():
            if field.name() in self.dataFields:
                atts.append(field)
        # Also add fields for the desurveyed coordinates
        atts.append(QgsField("_From_x",  QVariant.Double, "double", 12, 3))
        atts.append(QgsField("_From_y",  QVariant.Double, "double", 12, 3))
        atts.append(QgsField("_From_z",  QVariant.Double, "double", 12, 3))
        atts.append(QgsField("_To_x",  QVariant.Double, "double", 12, 3))
        atts.append(QgsField("_To_y",  QVariant.Double, "double", 12, 3))
        atts.append(QgsField("_To_z",  QVariant.Double, "double", 12, 3))
        
        # Add all the attributes to the new layer
        dp = layer.dataProvider()
        dp.addAttributes(atts)
        
        # Tell the vector layer to fetch changes from the provider
        layer.updateFields() 

        return layer

    # Read all the saved DrillManager parameters from the QGIS project        
    def readProjectData(self):
        self.defaultSectionWidth = readProjectNum("DefaultSectionWidth", 50)
        self.defaultSectionStep= readProjectNum("DefaultSectionStep", 50)
        self.desurveyLength = readProjectNum("DesurveyLength", 1)
        self.downDipNegative = readProjectBool("DownDipNegative", True)
        self.collarLayer = readProjectLayer("CollarLayer")
        self.surveyLayer = readProjectLayer("SurveyLayer")
        self.dataLayer = readProjectLayer("DataLayer")
        self.traceLayer = readProjectLayer("TraceLayer")
        self.collarId = readProjectField("CollarID")
        self.collarDepth = readProjectField("CollarDepth")
        self.collarEast = readProjectField("CollarEast")
        self.collarNorth = readProjectField("CollarNorth")
        self.collarElev = readProjectField("CollarElev")
        self.collarAz = readProjectField("CollarAz")
        self.collarDip = readProjectField("CollarDip")
        self.surveyId = readProjectField("SurveyID")
        self.surveyDepth = readProjectField("SurveyDepth")
        self.surveyAz = readProjectField("SurveyAz")
        self.surveyDip = readProjectField("SurveyDip")
        self.dataId = readProjectField("DataID")
        self.dataFrom = readProjectField("DataFrom")
        self.dataTo = readProjectField("DataTo")
        self.dataSuffix = readProjectField("DataSuffix")
        
        # Collar layer might have changed, so re-open the log file
        self.openLogFile()

    # Write all DrillManager parameters to the QGIS project file
    def writeProjectData(self):
        writeProjectData("DefaultSectionWidth", self.defaultSectionWidth)
        writeProjectData("DefaultSectionStep", self.defaultSectionStep)
        writeProjectData("DesurveyLength", self.desurveyLength)
        writeProjectData("DownDepthNegative", self.downDipNegative)
        writeProjectLayer("CollarLayer", self.collarLayer)
        writeProjectLayer("SurveyLayer", self.surveyLayer)
        writeProjectLayer("DataLayer", self.dataLayer)
        writeProjectLayer("TraceLayer", self.traceLayer)
        writeProjectField("CollarID", self.collarId)
        writeProjectField("CollarDepth", self.collarDepth)
        writeProjectField("CollarEast", self.collarEast)
        writeProjectField("CollarNorth", self.collarNorth)
        writeProjectField("CollarElev", self.collarElev)
        writeProjectField("CollarAz", self.collarAz)
        writeProjectField("CollarDip", self.collarDip)
        writeProjectField("SurveyID", self.surveyId)
        writeProjectField("SurveyDepth", self.surveyDepth)
        writeProjectField("SurveyAz", self.surveyAz)
        writeProjectField("SurveyDip", self.surveyDip)
        writeProjectField("DataID", self.dataId)
        writeProjectField("DataFrom", self.dataFrom)
        writeProjectField("DataTo", self.dataTo)
        writeProjectField("DataSuffix", self.dataSuffix)
    
