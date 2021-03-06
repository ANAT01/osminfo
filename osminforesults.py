# -*- coding: utf-8 -*-
#******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all 
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# Author:   Alexander Lisovenko, alexander.lisovenko@nextgis.ru
# *****************************************************************************
# Copyright (c) 2012-2015. NextGIS, info@nextgis.com
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/licenses/>. You can also obtain it by writing
# to the Free Software Foundation, 51 Franklin Street, Suite 500 Boston,
# MA 02110-1335 USA.
#
#******************************************************************************
import json

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtNetwork import QNetworkRequest
from qgis.core import *

from osminfo_worker import Worker

FeatureItemType = 1001
TagItemType = 1002

class ResultsDialog(QDockWidget):
    def __init__(self, title, result_render, parent=None):
        self.__rb = result_render
        self.__selected_id = None
        self.__rel_reply = None
        self.worker = None
        QDockWidget.__init__(self, title, parent)
        self.__mainWidget = QWidget()

        self.__layout = QVBoxLayout(self.__mainWidget)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.__resultsTree.customContextMenuRequested.connect(self.openMenu)

        self.__resultsTree.setMinimumSize(350, 250)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels([self.tr('Feature/Key'), self.tr('Value')])
        self.__resultsTree.header().setResizeMode(QHeaderView.ResizeToContents)
        self.__resultsTree.header().setStretchLastSection(False)
        self.__resultsTree.itemSelectionChanged.connect(self.selItemChanged)
        self.__layout.addWidget(self.__resultsTree)
        self.__resultsTree.clear()

        self.setWidget(self.__mainWidget)

        overrideLocale = QSettings().value('locale/overrideFlag', False, type=bool)
        if not overrideLocale:
            self.qgisLocale = QLocale.system().name()[:2]
        else:
            self.qgisLocale = QSettings().value('locale/userLocale', '', type=unicode)[:2]

    def openMenu(self, position):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) > 0 and selected_items[0].type() in [TagItemType, FeatureItemType]:
            menu = QMenu()
            actionZoom = QAction(QIcon(':/plugins/osminfo/icons/zoom2feature.png'), self.tr('Zoom to feature'), self)
            menu.addAction(actionZoom)
            actionZoom.setStatusTip(self.tr('Zoom to selected item'))
            actionZoom.triggered.connect(self.zoom2feature)
            menu.exec_(self.__resultsTree.viewport().mapToGlobal(position))
    
    def zoom2feature(self):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) > 0:
            item = selected_items[0]
            # if selected tag - use parent
            if item.type() == TagItemType:
                item = item.parent()
            if item and item.type() == FeatureItemType:
                element = item.data(0, Qt.UserRole)
                if element and 'bounds' in element:
                    b_el = element['bounds']
                    new_extent = QgsRectangle(b_el['minlon'], b_el['minlat'], b_el['maxlon'], b_el['maxlat'])
                    self.__rb.zoom_to_bbox(new_extent)


    def getInfo(self, xx, yy):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([self.tr('Loading....')]))

        if self.worker:
            self.worker.gotData.disconnect(self.showData)
            self.worker.gotError.disconnect(self.showError)
            self.worker.quit()
            self.worker.deleteLater()

        worker = Worker(xx, yy)
        worker.gotData.connect(self.showData)
        worker.gotError.connect(self.showError)
        worker.start()

        self.worker = worker

    def showError(self, msg):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([msg]))

    def showData(self, l1, l2):
        self.__resultsTree.clear()

        near = QTreeWidgetItem([self.tr('Nearby features')])
        self.__resultsTree.addTopLevelItem(near)
        self.__resultsTree.expandItem(near)

        index = 1

        for element in l1:
            # print element
            try:
                elementTags = element[u'tags']
                elementTitle = elementTags.get(
                    u'name:%s' % self.qgisLocale,
                    elementTags.get(
                        u'name',
                        elementTags.get(
                            u"id",
                            ""
                        )
                    )
                )
                if not elementTitle:
                    if 'building' in elementTags.keys():
                        if 'addr:street' in elementTags.keys() and 'addr:housenumber' in elementTags.keys():
                            elementTitle = elementTags['addr:street'] + ', ' + elementTags['addr:housenumber']
                        else:
                            elementTitle = 'building'
                    elif 'highway' in elementTags.keys():
                        elementTitle = 'highway:' + elementTags['highway']
                    elif 'amenity' in elementTags.keys():
                        elementTitle = elementTags['amenity']
                    else:
                        elementTitle = elementTags[0]
                elementItem = QTreeWidgetItem(near, [elementTitle], FeatureItemType)
                elementItem.setData(0, Qt.UserRole, element)
                for tag in sorted(elementTags.items()):
                    elementItem.addChild(QTreeWidgetItem(tag, TagItemType))

                self.__resultsTree.addTopLevelItem(elementItem)
                #self.__resultsTree.expandItem(elementItem)
                index += 1
            except Exception as e:
                print e

        isin = QTreeWidgetItem([self.tr('Is inside')])
        self.__resultsTree.addTopLevelItem(isin)
        self.__resultsTree.expandItem(isin)

        l2Sorted = sorted(
            l2,
            key=lambda element: QgsGeometry().fromRect(
                QgsRectangle(
                    element['bounds']['minlon'],
                    element['bounds']['minlat'],
                    element['bounds']['maxlon'],
                    element['bounds']['maxlat'])
            ).area()
        )

        for element in l2Sorted:
            # print element
            try:
                elementTags = element[u'tags']
                elementTitle = elementTags.get(
                    u'name:%s' % self.qgisLocale,
                    elementTags.get(
                        u'name',
                        elementTags.get(
                            u"id",
                            ""
                        )
                    )
                )
                elementItem = QTreeWidgetItem(isin, [elementTitle], FeatureItemType)
                elementItem.setData(0, Qt.UserRole, element)
                for tag in sorted(elementTags.items()):
                    elementItem.addChild(QTreeWidgetItem(tag, TagItemType))

                self.__resultsTree.addTopLevelItem(elementItem)
                index += 1
            except Exception as e:
                print e

    def selItemChanged(self):
        selection = self.__resultsTree.selectedItems()
        if not selection:
            return
        item = selection[0]
        # if selected tag - use parent
        if item.type() == TagItemType:
            item = item.parent()
        # if already selected - exit
        if self.__selected_id == item:
            return
        # clear old highlights
        self.__rb.clear_feature()
        # set new
        if item and item.type() == FeatureItemType:
            self.__selected_id = item
            element = item.data(0, Qt.UserRole)
            if element:
                if element['type'] == 'node':
                    geom = QgsGeometry.fromPoint(QgsPoint(element['lon'], element['lat']))
                if element['type'] == 'way':
                    geom = QgsGeometry.fromPolyline([QgsPoint(g['lon'], g['lat']) for g in element['geometry'] if g!='null'])
                if element['type'] == 'relation':
                    self.sendRelationRequest(element['id'])
                    return
                self.__rb.show_feature(geom)

    def sendRelationRequest(self, relation_id):
        if self.__rel_reply:
            try:
                self.__rel_reply.abort()
                self.__rel_reply.finished.disconnect(self.showRelationGeom)
            except:
                pass
        url = 'http://overpass-api.de/api/interpreter'
        rel_request = QNetworkRequest(QUrl(url))
        qnam = QgsNetworkAccessManager.instance()
        request_data = '[out:json];rel(%s);out geom;' % (relation_id)
        self.__rel_reply = qnam.post(rel_request, QByteArray(request_data))
        self.__rel_reply.finished.connect(self.showRelationGeom)
        self.__rel_reply.error.connect(lambda: 'ok')

    def showRelationGeom(self):
        rel_data = ()
        try:
            data = self.__rel_reply.readAll()
            self.__rel_reply.finished.disconnect(self.showRelationGeom)
            rel_data = json.loads(str(data))
        except:
            pass
        if 'elements' in rel_data and len(rel_data['elements']) > 0:
            element = rel_data['elements'][0]
            if 'members' in element:
                lines = []
                for member in element['members']:
                    if member['type'] == 'way' and member['role'] == 'outer':
                        lines.append([QgsPoint(g['lon'], g['lat']) for g in member['geometry'] if g != 'null'])
                geom =QgsGeometry.fromMultiPolyline(lines)
                self.__rb.show_feature(geom)