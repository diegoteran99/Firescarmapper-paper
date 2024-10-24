# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Example
                                 A QGIS plugin
 an example
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-10-07
        git sha              : $Format:%H$
        copyright            : (C) 2024 by diego
        email                : diego@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
"""
TODO:
- hacer que se utilicen los archivos ya generados de la carpeta results 
- mejorar el diagrama que se muestra para que sea mas representativo
"""
from .resources import *
from .example_dialog import ExampleDialog
import os.path
from qgis.core import (Qgis, QgsProcessingAlgorithm,QgsProject, QgsRasterLayer, QgsProcessingException, 
                       QgsSingleBandPseudoColorRenderer, QgsRasterMinMaxOrigin, QgsProcessingFeedback, 
                       QgsColorRampShader, QgsRasterShader, QgsStyle, QgsContrastEnhancement)
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
import torch
from .firescarmapping.model_u_net import model, device
from .firescarmapping.as_dataset import create_datasetAS
from .firescarmapping.dataset_128 import create_dataset128
import numpy as np
from torch.utils.data import DataLoader
import os
from osgeo import gdal, gdal_array
import requests
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog, QVBoxLayout, QPushButton, QFileDialog
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QFileDialog, QLabel, QDialog, QTextEdit, QHBoxLayout, QMessageBox, QComboBox
import geopandas as gpd
from geopandas import GeoDataFrame


class FireScarMapper(QgsProcessingAlgorithm):    
    def processAlgorithm(self, parameters, context, feedback):
        before_paths, burnt_paths, shp_file, datatype, cropped = parameters['BeforeRasters'], parameters['AfterRasters'], parameters['Shapefile'], parameters['ModelScale'], parameters['AlreadyCropped']

        not_cropped_paths = before_paths + burnt_paths
        before, burnt, cropped_before_paths, cropped_burnt_paths = [], [], [], []
        
        results_dir = os.path.join(os.path.dirname(__file__), 'results')
        model_scale_dir = os.path.join(results_dir, datatype)

        # Crear el directorio 'results' si no existe
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
            feedback.pushInfo(f"Created main results directory at: {results_dir}")

        if not os.path.exists(model_scale_dir):
            os.makedirs(model_scale_dir)
            feedback.pushInfo(f"Created directory for specified model at: {model_scale_dir}")
        
        
        for i in range(len(before_paths)):
            before_name = parameters['BeforeRasters'][i].split("/")[-1]
            burnt_name = parameters['AfterRasters'][i].split("/")[-1]
            image_id = before_name.split('_')[2]  # Suponiendo que el ID está en la tercera parte del nombre
            
            if cropped == False:
                # Obtener las coordenadas desde el archivo .shp usando el ID de la imagen
                if datatype == "AS":
                    bounds = self.get_bounds_from_shp(shp_file, image_id)
                
                # Generar rutas para las imágenes recortadas
                cropped_before_path = os.path.join(os.path.dirname(__file__), f'results/{datatype}', before_name.replace(".tif","_clip.tif"))
                cropped_before_paths.append(cropped_before_path)
                #feedback.pushInfo(f"Cropping before image to: {cropped_before_path}")
                cropped_burnt_path = os.path.join(os.path.dirname(__file__), f'results/{datatype}', burnt_name.replace(".tif","_clip.tif"))
                cropped_burnt_paths.append(cropped_burnt_path)
                #feedback.pushInfo(f"Cropping burnt image to: {cropped_burnt_path}")
               
                # Recortar las imágenes usando las coordenadas
                
                if datatype == "AS":
                    self.crop_image_with_bounds(before_paths[i], cropped_before_path, bounds)
                    #feedback.pushInfo(f"Checking cropped before image at: {cropped_before_path}")
                    if not os.path.exists(cropped_before_path):
                        raise QgsProcessingException(f"Failed to crop before image: {cropped_before_path}")

                    self.crop_image_with_bounds(burnt_paths[i], cropped_burnt_path, bounds)
                    #feedback.pushInfo(f"Checking cropped burnt image at: {cropped_burnt_path}")
                    if not os.path.exists(cropped_burnt_path):
                        raise QgsProcessingException(f"Failed to crop burnt image: {cropped_burnt_path}")
                
                else:
                    self.cropping128_with_ignition_point(shp_file, before_paths[i], cropped_before_path, image_id)
                    #feedback.pushInfo(f"Checking cropped before image at: {cropped_before_path}")
                    if not os.path.exists(cropped_before_path):
                        raise QgsProcessingException(f"Failed to crop before image: {cropped_before_path}")
                    
                    self.cropping128_with_ignition_point(shp_file, burnt_paths[i], cropped_burnt_path, image_id)
                    #feedback.pushInfo(f"Checking cropped burnt image at: {cropped_burnt_path}")
                    if not os.path.exists(cropped_burnt_path):
                        raise QgsProcessingException(f"Failed to crop burnt image: {cropped_burnt_path}")
                

                # Cargar las imágenes recortadas como capas de QGIS
                before.append(QgsRasterLayer(cropped_before_path, before_name.replace(".tif","_clip.tif"), "gdal"))
                burnt.append(QgsRasterLayer(cropped_burnt_path, burnt_name.replace(".tif","_clip.tif"), "gdal"))
            else:
                before.append(QgsRasterLayer(parameters['BeforeRasters'][i], before_name, "gdal"))
                burnt.append(QgsRasterLayer(parameters['AfterRasters'][i], burnt_name, "gdal"))
                
        if cropped == False:
            cropped_paths = cropped_before_paths + cropped_burnt_paths
            if not os.path.exists(cropped_before_path):
                raise QgsProcessingException(f"Cropped image not found: {cropped_before_path}")
            if not os.path.exists(cropped_burnt_path):
                raise QgsProcessingException(f"Cropped image not found: {cropped_burnt_path}")
        
        # Asegurarse de que las capas sean listas de QgsRasterLayer
        if not isinstance(before, list) or not isinstance(burnt, list):
            raise QgsProcessingException("Input rasters must be lists of QgsRasterLayer")

        if len(before) != len(burnt):
            raise QgsProcessingException("The number of before and burnt rasters must be the same")
        
        rasters = []
        if cropped == False:
            for i, layer in enumerate(before + burnt):
                adict = {
                    "type": "before" if i < len(before) else "burnt",
                    "id": i,
                    "qid": layer.id(),
                    "name": layer.name()[8:-9],
                    "data": self.get_rlayer_data(layer),
                    "layer": layer,
                    "path": cropped_paths[i],
                    "not_cropped_path": not_cropped_paths[i],
                    "output_path":os.path.join(model_scale_dir, f"FireScar_{layer.name()[8:-9]}.tif")
                }
                adict.update(self.get_rlayer_info(layer))
                rasters += [adict]
               
        else:
            for i, layer in enumerate(before + burnt):
                adict = {
                    "type": "before" if i < len(before) else "burnt",
                    "id": i,
                    "qid": layer.id(),
                    "name": layer.name()[8:-9],
                    "data": self.get_rlayer_data(layer),
                    "layer": layer,
                    "path": not_cropped_paths[i],
                    "not_cropped_path": not_cropped_paths[i],
                    "output_path":os.path.join(model_scale_dir, f"FireScar_{layer.name()[8:-9]}.tif")
                }
                adict.update(self.get_rlayer_info(layer))
                rasters += [adict]

        before_files, after_files, before_files_data, after_files_data = [], [], [], []
      
        #Order rasters
        for i in range(len(rasters)//2):
            before_files.append(rasters[i])
            before_files_data.append(before_files[i]['data'])
            for j in range(len(rasters)//2): #starts iterating from the second half
                if rasters[i]['name'] == rasters[j + (len(rasters)//2)]['name']:
                    after_files.append(rasters[j + (len(rasters)//2)])
                    after_files_data.append(after_files[i]['data'])

        if datatype == "AS":
            model_path = os.path.join(os.path.dirname(__file__), 'firescarmapping', 'ep25_lr1e-04_bs16_021__as_std_adam_f01_13_07_x3.model')
            model_download_url = "https://fire2a-firescar-as-model.s3.amazonaws.com/ep25_lr1e-04_bs16_021__as_std_adam_f01_13_07_x3.model"
        else:
            model_path = os.path.join(os.path.dirname(__file__), 'firescarmapping', 'ep25_lr1e-04_bs16_014_128_std_25_08_mult3_adam01.model')
            model_download_url = "https://fire2a-firescar-as-model.s3.amazonaws.com/ep25_lr1e-04_bs16_014_128_std_25_08_mult3_adam01.model"
        
        if not os.path.exists(model_path):
            feedback.pushInfo("Model not found. Initializing download...")
            self.download_model(model_path, model_download_url, feedback)

        device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
        np.random.seed(3)
        torch.manual_seed(3)    
        
        
        if datatype == "128":
            data_eval = create_dataset128(before_files_data, after_files_data, mult=1)
        else:
            data_eval = create_datasetAS(before_files_data, after_files_data, mult=1)
        
        batch_size = 1 # 1 to create diagnostic images, any value otherwise
        all_dl = DataLoader(data_eval, batch_size=batch_size)

        model.eval()

        for i, batch in enumerate(all_dl):
            x = batch['img'].float().to(device)
            output = model(x).cpu()

            # obtain binary prediction map
            pred = np.zeros(output.shape)
            pred[output >= 0] = 1

            generated_matrix = pred[0][0]
            
            if before_files[i]['output_path']:
                
                group_name = before_files[i]['name'].split("_")[0] + "_" + before_files[i]['name'].split("_")[1] + " (" + datatype + ")"
                root = QgsProject.instance().layerTreeRoot()
                group = root.findGroup(group_name)
                if not group:
                    group = root.addGroup(group_name)
                
                # Colapsar el grupo para que se muestre minimizado en el panel de capas
                project_instance = QgsProject.instance()
                layer_tree = project_instance.layerTreeRoot().findGroup(group_name)
                if layer_tree:
                    layer_tree.setExpanded(False)

                self.writeRaster(generated_matrix, before_files[i]['output_path'], before_files[i], feedback)
                self.addRasterLayer(before_files[i]['output_path'],f"FireScar_{before_files[i]['name']}", group, context)
                self.addRasterLayer(after_files[i]['not_cropped_path'],f"ImgPosF_{after_files[i]['name']}", group, context)
                self.addRasterLayer(before_files[i]['not_cropped_path'],f"ImgPreF_{before_files[i]['name']}", group, context)
        return {}
        
    
    def download_model(self, model_path, download_url, feedback):
        """Download the model from Amazon S3 with progress feedback."""
        
        def save_response_content(response, destination, feedback, total_size):
            """Guardar el contenido descargado en el archivo de destino con retroalimentación de progreso."""
            CHUNK_SIZE = 1048576  # 1 MB
            bytes_downloaded = 0
            
            with open(destination, "wb") as f:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if chunk:  # Filtrar los "keep-alive" chunks vacíos
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        # Calcular el porcentaje de descarga completada
                        progress = (bytes_downloaded / total_size) * 100

                        # Usar setProgress solo si está disponible en el feedback
                        if hasattr(feedback, 'setProgress'):
                            feedback.setProgress(int(progress))

                        # Informar el progreso en MB
                        feedback.pushInfo(f"Downloaded {bytes_downloaded // (1024 * 1024)} MB of {total_size // (1024 * 1024)} MB")

        # Iniciar una sesión persistente para reutilizar la conexión
        session = requests.Session()
        
        try:
            # Intentar realizar la solicitud con un timeout y streaming habilitado
            response = session.get(download_url, stream=True, timeout=30)
            response.raise_for_status()  # Lanza una excepción si la descarga falla

            # Obtener el tamaño total del archivo desde los encabezados de la respuesta
            total_size = int(response.headers.get('Content-Length', 0))
            if total_size == 0:
                raise requests.exceptions.RequestException("Unable to determine the file size.")

            # Informar sobre el inicio de la descarga
            feedback.pushInfo(f"Downloading model to {model_path} ({total_size // (1024 * 1024)} MB)")

            # Guardar el contenido descargado
            save_response_content(response, model_path, feedback, total_size)

            # Informar que la descarga ha sido exitosa
            feedback.pushInfo(f"Model successfully downloaded and saved at {model_path}")
        
        except requests.exceptions.RequestException as e:
            # Manejo de cualquier error que pueda ocurrir durante la solicitud
            feedback.pushInfo(f"Failed to download model: {str(e)}")
    
    def get_bounds_from_shp(self, shp_file, image_id):
        """Buscar las coordenadas de recorte en el archivo .shp usando el ID de la imagen."""
        # Leer el archivo .shp
        shapefile = gpd.read_file(shp_file)

        # Filtrar según el ID de la imagen
        filtered_row = shapefile[shapefile['FireID'] == image_id]
        
        if filtered_row.empty:
            raise ValueError(f"ID {image_id} not found in shapefile")

        # Extraer los valores de las coordenadas
        north_bound = filtered_row['NorthBound'].values[0]
        south_bound = filtered_row['SouthBound'].values[0]
        west_bound = filtered_row['WestBoundL'].values[0]
        east_bound = filtered_row['EastBoundL'].values[0]

        return north_bound, south_bound, west_bound, east_bound
   
    def crop_image_with_bounds(self, image_path, output_path, bounds):
        """Recortar la imagen usando gdal y las coordenadas obtenidas del archivo .shp."""
        
        # Abrir la imagen con gdal
        image = gdal.Open(image_path)
        
        # Definir los parámetros de geotransformación y las coordenadas de recorte
        gt = image.GetGeoTransform()
        
        min_x = bounds[2]  # west_bound
        max_x = bounds[3]  # east_bound
        min_y = bounds[1]  # south_bound
        max_y = bounds[0]  # north_bound

        # Ejecutar el recorte utilizando gdal.Warp
        gdal.Warp(output_path, 
                image, 
                outputBounds=(min_x, min_y, max_x, max_y),
                dstNodata=0)
        
        # Cerrar la imagen de origen
        image = None

    def cropping128_with_ignition_point(self, shp_file, ipname, output, fire_id):
        """
        Clip the satellite raster around the ignition point using the specified size.

        Parameters:
        shp_file: str - Path to the shapefile containing the ignition point
        ipname: str - Path to the raster to be clipped
        output: str - Path to save the cropped raster
        fire_id: str - The fire ID used to match the ignition point in the shapefile
        """
        size = 128
        # Step 1: Extract the ignition point coordinates from the shapefile using the fire ID
        ignition_point = self.get_ignition_point_from_shp(shp_file, fire_id)

        # Step 2: Open the input raster to get its geotransform and calculate bounds
        inDs = gdal.Open(ipname)
        ulx, xres, xskew, uly, yskew, yres = inDs.GetGeoTransform()

        # Get the coordinates of the ignition point
        ignition_x, ignition_y = ignition_point

        # Step 3: Calculate the bounds of the cropping window around the ignition point
        min_x = ignition_x - (size / 2) * xres
        max_x = ignition_x + (size / 2) * xres
        min_y = ignition_y + (size / 2) * yres  # yres is negative, hence addition
        max_y = ignition_y - (size / 2) * yres

        # Step 4: Perform the cropping using gdal.Warp
        gdal.Warp(output, inDs, outputBounds=(min_x, min_y, max_x, max_y), dstNodata=0)

        # Close the dataset
        inDs = None

    def get_ignition_point_from_shp(self, shp_file, fire_id):
        """
        Extract the ignition point coordinates from the shapefile using the fire ID.

        Parameters:
        shp_file: str - Path to the shapefile
        fire_id: str - The fire ID used to filter the correct row
        
        Returns:
        tuple: (longitude, latitude) coordinates of the ignition point
        """
        # Read the shapefile
        gdf = GeoDataFrame.from_file(shp_file)

        # Filter the shapefile using the fire ID
        filtered_row = gdf[gdf['FireID'] == fire_id]

        if filtered_row.empty:
            raise ValueError(f"ID {fire_id} not found in the shapefile.")

        # Extract the latitude and longitude from the columns 'Latitude_[' and 'Longitude_'
        ignition_latitude = filtered_row['Latitude_['].values[0]
        ignition_longitude = filtered_row['Longitude_'].values[0]

        return ignition_longitude, ignition_latitude    

    def qgis2numpy_dtype(self, qgis_dtype: Qgis.DataType) -> np.dtype:
        """Conver QGIS data type to corresponding numpy data type
        https://raw.githubusercontent.com/PUTvision/qgis-plugin-deepness/fbc99f02f7f065b2f6157da485bef589f611ea60/src/deepness/processing/processing_utils.py
        This is modified and extended copy of GDALDataType.

        * `UnknownDataType: Unknown or unspecified type
        * `Byte: Eight bit unsigned integer (quint8)
        * `Int8: Eight bit signed integer (qint8) (added in QGIS 3.30)
        * `UInt16: Sixteen bit unsigned integer (quint16)
        * `Int16: Sixteen bit signed integer (qint16)
        * `UInt32: Thirty two bit unsigned integer (quint32)
        * `Int32: Thirty two bit signed integer (qint32)
        * `Float32: Thirty two bit floating point (float)
        * `Float64: Sixty four bit floating point (double)
        * `CInt16: Complex Int16
        * `CInt32: Complex Int32
        * `CFloat32: Complex Float32
        * `CFloat64: Complex Float64
        * `ARGB32: Color, alpha, red, green, blue, 4 bytes the same as QImage.Format_ARGB32
        * `ARGB32_Premultiplied: Color, alpha, red, green, blue, 4 bytes  the same as QImage.Format_ARGB32_Premultiplied
        """
        if qgis_dtype == Qgis.DataType.Byte or qgis_dtype == "Byte":
            return np.uint8
        if qgis_dtype == Qgis.DataType.UInt16 or qgis_dtype == "UInt16":
            return np.uint16
        if qgis_dtype == Qgis.DataType.Int16 or qgis_dtype == "Int16":
            return np.int16
        if qgis_dtype == Qgis.DataType.Float32 or qgis_dtype == "Float32":
            return np.float32
        if qgis_dtype == Qgis.DataType.Float64 or qgis_dtype == "Float64":
            return np.float64

    def get_rlayer_info(self, layer: QgsRasterLayer):
        """Get raster layer info: width, height, extent, crs, cellsize_x, cellsize_y, nodata list, number of bands.

        Args:
            layer (QgsRasterLayer): A raster layer
        Returns:
            dict: raster layer info
        """
        provider = layer.dataProvider()
        ndv = []
        for band in range(1, layer.bandCount() + 1):
            ndv += [None]
            if provider.sourceHasNoDataValue(band):
                ndv[-1] = provider.sourceNoDataValue(band)
        return {
            "width": layer.width(),
            "height": layer.height(),
            "extent": layer.extent(),
            "crs": layer.crs(),
            "cellsize_x": layer.rasterUnitsPerPixelX(),
            "cellsize_y": layer.rasterUnitsPerPixelY(),
            "nodata": ndv,
            "bands": layer.bandCount(),
        }

    def get_rlayer_data(self, layer: QgsRasterLayer):
        """Get raster layer data (EVERY BAND) as numpy array; Also returns nodata value, width and height
        The user should check the shape of the data to determine if it is a single band or multiband raster.
        len(data.shape) == 2 for single band, len(data.shape) == 3 for multiband.

        Args:
            layer (QgsRasterLayer): A raster layer

        Returns:
            data (np.array): Raster data as numpy array
            nodata (None | list): No data value
            width (int): Raster width
            height (int): Raster height

        FIXME? can a multiband raster have different nodata values and/or data types for each band?
        TODO: make a band list as input
        """
        provider = layer.dataProvider()
        if layer.bandCount() == 1:
            block = provider.block(1, layer.extent(), layer.width(), layer.height())
            nodata = None
            if block.hasNoDataValue():
                nodata = block.noDataValue()
            np_dtype = self.qgis2numpy_dtype(provider.dataType(1))
            data = np.frombuffer(block.data(), dtype=np_dtype).reshape(layer.height(), layer.width())
        else:
            data = []
            nodata = []
            np_dtype = []
            for i in range(layer.bandCount()):
                block = provider.block(i + 1, layer.extent(), layer.width(), layer.height())
                nodata += [None]
                if block.hasNoDataValue():
                    nodata[-1] = block.noDataValue()
                np_dtype += [self.qgis2numpy_dtype(provider.dataType(i + 1))]
                data += [np.frombuffer(block.data(), dtype=np_dtype[-1]).reshape(layer.height(), layer.width())]
            # would different data types bug this next line?
            data = np.array(data)
        # return data, nodata, np_dtype
        return data

    def writeRaster(self, matrix, file_path, before_layer, feedback):

        # Get the dimensions of the raster before the fire
        width = before_layer["width"]
        height = before_layer["height"]

        # Create the output raster file
        driver = gdal.GetDriverByName('GTiff')
        raster = driver.Create(file_path, width, height, 1, gdal.GDT_Byte)

        if raster is None:
            raise QgsProcessingException("Failed to create raster file.")

        # Set the geotransformation and projection
        extent = before_layer["extent"]
        pixel_width = extent.width() / width
        pixel_height = extent.height() / height
        raster.SetGeoTransform((extent.xMinimum(), pixel_width, 0, extent.yMaximum(), 0, -pixel_height))
        raster.SetProjection(before_layer["crs"].toWkt())

        # Get the raster band
        band = raster.GetRasterBand(1)

        # Calculate the offset and size of the burn scar region to fit the raster
        start_row = 0
        start_col = 0
        matrix_height, matrix_width = matrix.shape

        if matrix_height > height:
            start_row = (matrix_height - height) // 2
            matrix_height = height
        if matrix_width > width:
            start_col = (matrix_width - width) // 2
            matrix_width = width

        # Crop the matrix to match the raster dimensions
        resized_matrix = matrix[start_row:start_row + matrix_height, start_col:start_col + matrix_width]

        # Write the matrix to the raster band
        try:
            gdal_array.BandWriteArray(band, resized_matrix, 0, 0)
        except ValueError as e:
            raise QgsProcessingException(f"Failed to write array to raster: {str(e)}")

        # Set the NoData value
        band.SetNoDataValue(0)
        
        # Ensure that the minimum and maximum values are updated
        band.ComputeStatistics(False)
        band.SetStatistics(0, 1, 0.5, 0.5)

        # Flush cache and close the raster
        band.FlushCache()
        raster.FlushCache()
        raster = None

        feedback.pushInfo(f"Raster written to {file_path}")

    def addRasterLayer(self, file_path, layer_name, group, context):
        """Añadir la capa raster al grupo en el proyecto."""
        layer = QgsRasterLayer(file_path, layer_name, "gdal")
        if not layer.isValid():
            raise QgsProcessingException(f"Failed to load raster layer from {file_path}")

        # Añadir la capa al proyecto sin mostrarla
        QgsProject.instance().addMapLayer(layer, False)
        group.addLayer(layer)

        # Si el nombre de la capa contiene "FireScar", cambiar el renderer a singleband pseudocolor
        if "FireScar" in layer_name:
            # Forzar el cálculo de las estadísticas de la banda para obtener los valores correctos
            provider = layer.dataProvider()
            stats = provider.bandStatistics(1, QgsRasterMinMaxOrigin.Estimated)
            min_value = stats.minimumValue
            max_value = stats.maximumValue

            # Crear un shader de color para interpolar entre colores
            shader = QgsRasterShader()
            color_ramp_shader = QgsColorRampShader(minimumValue=min_value, maximumValue=max_value)
            color_ramp_shader.setColorRampType(QgsColorRampShader.Interpolated)

            # Usar el estilo "Reds" de la lista de estilos de QGIS
            style = QgsStyle().defaultStyle()
            ramp = style.colorRamp('Reds')
            if ramp:
                color_ramp_shader.setSourceColorRamp(ramp)

            shader.setRasterShaderFunction(color_ramp_shader)

            # Crear el renderer con el shader
            renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)

            # Asignar el renderer a la capa
            layer.setRenderer(renderer)

            # Actualizar el rango de contraste para asegurarse de que se muestren correctamente
            layer.setContrastEnhancement(QgsContrastEnhancement.StretchToMinimumMaximum)

            # Forzar la actualización del renderizador
            layer.triggerRepaint()
            layer.reload()

    def name(self):
        return "firescarmapper"
    
    def displayName(self):
        return self.tr("Fire Scar Mapper")

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return FireScarMapper()


class LayerSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(800, 600) 

        # Descripción del proceso (añadido)
        self.description_label = QTextEdit(self)
        self.description_label.setReadOnly(True)
        self.description_label.setHtml(self.get_description())  # Set HTML content

        # Selector para imágenes pre-incendio
        self.pre_fire_button = QPushButton("Select Pre-Fire Images")
        self.pre_fire_button.clicked.connect(self.select_pre_fire_files)

        # Selector para imágenes post-incendio
        self.post_fire_button = QPushButton("Select Post-Fire Images")
        self.post_fire_button.clicked.connect(self.select_post_fire_files)

        # Añadir al diálogo la opción de seleccionar el archivo .shp
        self.shp_button = QPushButton("Select Shapefile")
        self.shp_button.clicked.connect(self.select_shp_file)

        # Campo de texto para mostrar las rutas seleccionadas de imágenes pre-incendio
        self.pre_fire_display = QTextEdit(self)
        self.pre_fire_display.setReadOnly(True)
        self.pre_fire_display.setPlaceholderText("Pre-fire images will be displayed here...")

        # Campo de texto para mostrar las rutas seleccionadas de imágenes post-incendio
        self.post_fire_display = QTextEdit(self)
        self.post_fire_display.setReadOnly(True)
        self.post_fire_display.setPlaceholderText("Post-fire images will be displayed here...")

        # Campo de texto para mostrar la ruta seleccionada del archivo .shp
        self.shp_display = QTextEdit(self)
        self.shp_display.setReadOnly(True)
        self.shp_display.setPlaceholderText("Shapefile will be displayed here...")

        # Selector para "Already cropped images" (True o False)
        self.cropped_label = QLabel("Already cropped images:")
        self.cropped_combo = QComboBox(self)
        self.cropped_combo.addItems(["False", "True"])

        # Selector para "Model Scale" (AS o 128)
        self.scale_label = QLabel("Model Scale:")
        self.scale_combo = QComboBox(self)
        self.scale_combo.addItems(["AS", "128"])

        # Botón para ejecutar el procesamiento
        self.run_button = QPushButton("Run Fire Scar Mapping")
        self.run_button.clicked.connect(self.run_fire_scar_mapping)

        # Layout para la izquierda: selectores de imágenes y campo de texto
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.pre_fire_button)
        left_layout.addWidget(self.pre_fire_display)

        left_layout.addWidget(self.post_fire_button)
        left_layout.addWidget(self.post_fire_display)
        # Añadir esto al layout
        left_layout.addWidget(self.shp_button)
        left_layout.addWidget(self.shp_display)
        
        left_layout.addWidget(self.cropped_label)
        left_layout.addWidget(self.cropped_combo)
        left_layout.addWidget(self.scale_label)
        left_layout.addWidget(self.scale_combo)

        left_layout.addWidget(self.run_button)

        # Layout principal: distribución en dos columnas (selectores a la izquierda, descripción a la derecha)
        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout)  # Columna izquierda
        main_layout.addWidget(self.description_label, stretch=1)  # Columna derecha con descripción

        self.setLayout(main_layout)

        # Almacenar las rutas de los archivos seleccionados
        self.pre_fire_files = []
        self.post_fire_files = []

    def get_description(self):
        """Obtener la descripción del plugin en formato HTML."""
        return """
            <h1>Fire Scar Mapper</h1><br>

            <b>Objective:</b> Generate fire scars using a pre-trained U-Net model and analyze the differences between pre- and post-fire satellite images.<br>

            <b>Process:</b> 
            Fire scars are identified by comparing the spectral differences between pre-fire and post-fire satellite images.<br>

            <b>Constraints:</b><br>
            (a) Pre- and post-fire images must have the same geographical extent and must be cropped to the affected area.<br>
            (b) Fire scars are calculated only within the affected areas.<br>

            <b>Inputs:</b><br>
            (i) A <b>pre-fire</b> raster layer containing the necessary spectral bands for analysis.<br>
            (ii) A <b>post-fire</b> raster layer containing the necessary spectral bands for analysis.<br>
            - Both images must be georeferenced and have the same spatial resolution.<br>

            <b>File Naming Format:</b><br>
            All image files must follow this naming convention:<br>
            <code>&lt;ImgPreF or ImgPosF&gt;_&lt;locality code&gt;_&lt;ID&gt;_&lt;threshold&gt;_&lt;year/month/day&gt;_clip.tif</code><br>
            For example:<br>
            <code>ImgPreF_CL-BI_ID74101_u350_19980330_clip.tif</code><br>

            <b>Considerations:</b><br>
            - The segmentation model is pre-trained and stored locally, and it will only be downloaded when necessary.<br>
            - In the pre- and post-fire image layers, the red and blue bands are swapped. You can fix this manually by adjusting the symbology properties of each layer.<br>

            <b>Image Example:</b><br>
            <img src=":/plugins/example/images/diagrama_2_plugin.png" alt="Example Image" width="500" height="300"><br>

        """

    def select_pre_fire_files(self):
        """Seleccionar las imágenes pre-incendio y mostrarlas en el campo de texto."""
        self.pre_fire_files, _ = QFileDialog.getOpenFileNames(self, "Select Pre-Fire Images", "", "Images (*.tif *.jpg *.png)")
        if self.pre_fire_files:
            self.pre_fire_display.setText("\n".join(self.pre_fire_files))

    def select_post_fire_files(self):
        """Seleccionar las imágenes post-incendio y mostrarlas en el campo de texto."""
        self.post_fire_files, _ = QFileDialog.getOpenFileNames(self, "Select Post-Fire Images", "", "Images (*.tif *.jpg *.png)")
        if self.post_fire_files:
            self.post_fire_display.setText("\n".join(self.post_fire_files))

    def select_shp_file(self):
        """Seleccionar el archivo .shp que contiene las coordenadas."""
        self.shp_file, _ = QFileDialog.getOpenFileName(self, "Select Shapefile", "", "Shapefile (*.shp)")
        if self.shp_file:
            self.shp_display.setText(self.shp_file)


    def run_fire_scar_mapping(self):
        """Ejecutar el procesamiento una vez seleccionadas las imágenes."""
        pre_fire_files = self.pre_fire_files
        post_fire_files = self.post_fire_files
        shp_file = self.shp_file  # Añadir el archivo .shp

        already_cropped = self.cropped_combo.currentText() == "True"
        model_scale = self.scale_combo.currentText()

        # Verificar que se hayan seleccionado imágenes y el shapefile
        if not pre_fire_files or not post_fire_files or not shp_file:
            QMessageBox.warning(self, "Error", "Please select both pre-fire, post-fire images and a shapefile.")
            return

        # Crear un feedback para mostrar el progreso y los mensajes
        feedback = QgsProcessingFeedback()

        # Ejecutar el algoritmo de FireScarMapper
        scar_mapper = FireScarMapper()

        parameters = {
            'BeforeRasters': pre_fire_files,
            'AfterRasters': post_fire_files,
            'Shapefile': shp_file,  # Agregar shapefile a los parámetros
            'AlreadyCropped': already_cropped,
            'ModelScale': model_scale,
            'OutputScars': os.path.join(os.path.dirname(__file__), f'results/{model_scale}', 'OutputScar.tif')
        }

        # Pasamos el feedback para evitar el error
        scar_mapper.processAlgorithm(parameters, context=None, feedback=feedback)

        feedback.pushInfo("Fire scar mapping process completed successfully.")

        self.close()


class Example:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Example_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Example')

        # Check if plugin was started the first time in current QGIS session
        self.first_start = None

    def tr(self, message):
        """Get the translation for a string using Qt translation API."""
        return QCoreApplication.translate('Example', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar."""
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = ':/plugins/example/icon.png'

        # Crear un botón para disparar el diálogo de selección y procesamiento
        self.add_action(
            icon_path,
            text=self.tr(u'Generate Fire Scars'),
            callback=self.show_layer_selection_dialog,  # Cambiado aquí
            parent=self.iface.mainWindow()
        )

        self.first_start = True

    def show_layer_selection_dialog(self):
        """Muestra el diálogo para seleccionar las capas y ejecutar el mapeo."""
        dialog = LayerSelectionDialog(self.iface.mainWindow())  # Asegúrate de pasar el parent correcto
        dialog.exec_()  # Muestra la ventana de diálogo

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Example'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""
        # Crear la clase FireScarMapper y registrarla en el contexto de procesamiento
        scar_mapper = FireScarMapper()
        scar_mapper.processAlgorithm({}, self.iface, feedback=self.iface.messageBar())

        # Mostrar cualquier mensaje en el diálogo
        if self.first_start:
            self.first_start = False
            self.dlg = ExampleDialog()

        # Mostrar el diálogo
        self.dlg.show()
        result = self.dlg.exec_()
        if result:
            pass