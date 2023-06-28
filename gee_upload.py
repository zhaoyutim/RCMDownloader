import glob
import multiprocessing
import os
import subprocess
import sys
sys.path.append('C:\\Users\\Yu\\.snap\\snap-python')
from osgeo import gdal
from snappy import ProductIO, HashMap, GPF

def upload_to_gcloud(file):
    print('Upload to gcloud')
    file_name = file.split('\\')[-1]
    upload_cmd = 'gsutil cp ' + file + ' gs://ai4wildfire/rcm/'+ file_name
    print(upload_cmd)
    os.system(upload_cmd)
    print('finish uploading' + file_name)


def upload_to_gee(file):
    print('start uploading to gee')
    file_name = file.split('\\')[-1]
    date = file_name.split('_')[-5]
    date = date[:4]+'-'+date[4:6]+'-'+date[6:]
    time_start = date + 'T10:00:00'
    cmd = 'earthengine upload image --time_start ' + time_start + ' --asset_id=projects/rcm-data/assets/rcm-data/' + file_name[:-4] + ' --pyramiding_policy=sample gs://ai4wildfire/rcm/'+ file_name
    print(cmd)
    subprocess.call(cmd.split())
    print('Uploading in progress for image ' + time_start)

def upload(file):
    upload_to_gcloud(file)
    upload_to_gee(file)

def upload_in_parallel(import_all=True, filepath='data/subset'):
    if import_all:
        file_list = glob.glob(os.path.join(filepath, '*.tif'))
    else:
        log_path = 'log/sanity_check_gee*.log'
        log_list = glob.glob(log_path)
        log_list.sort()
        with open(log_list[-1]) as f:
            f = f.readlines()
        file_list = []
        for line in f:
            file_list.append(os.path.join(filepath, line.split('_')[1],line.split('_')[2].replace('\n', '')+'.tif'))

    results = []
    with multiprocessing.Pool(processes=8) as pool:
        for file in file_list:
            result = pool.apply_async(upload, (file,))
            results.append(result)
        results = [result.get() for result in results if result is not None]

def upload_by_log(filepath='data/subset'):
    with open('log/error', 'r') as f:
        file = f.read().split('\n')

    def get_id(dir_str):
        return dir_str.split('/')[1]

    target_ids = list(map(get_id, file))

    def get_date(dir_str):
        return dir_str.split('/')[-1][:10]

    target_dates = list(map(get_date, file))
    for i, target_id in enumerate(target_ids):
        tif_list = glob.glob(os.path.join(filepath, target_id, 'VNPIMG' + target_dates[i] + '*.tif'))
        for tif_file in tif_list:
            os.system('geeadd delete --id '+'projects/proj5-dataset/assets/proj5_dataset/'+target_id+'_'+tif_file.split('/')[-1][:-4])
            upload(tif_file)

def sar_tc_sn(file_path='/Users/zhaoyu/PycharmProjects/eodms-cli/data/'):

    file_list = glob.glob(os.path.join(file_path, '*.zip'))
    for file in file_list:
        file_name=file.split('/')[-1].split('.')[0]
        # load the Sentinel-1 image
        product = ProductIO.readProduct(file)

        # create a HashMap to hold the parameters for the speckle filter
        speckle_parameters = HashMap()
        speckle_parameters.put('filter', 'Lee')
        speckle_parameters.put('filterSizeX', 3)
        speckle_parameters.put('filterSizeY', 3)
        speckle_parameters.put('dampingFactor', 2)
        speckle_parameters.put('windowSize', '7x7')
        speckle_parameters.put('estimateENL', 'true')
        speckle_parameters.put('enl', 1.0)
        speckle_parameters.put('numLooksStr', '1')
        speckle_parameters.put('targetWindowSizeStr', '3x3')
        speckle_parameters.put('sigmaStr', '0.9')
        speckle_parameters.put('anSize', '50')

        # create a HashMap to hold the parameters for the terrain correction
        terrain_parameters = HashMap()
        terrain_parameters.put('demName', 'SRTM 3Sec')
        terrain_parameters.put('pixelSpacingInMeter', 30.0)
        terrain_parameters.put('demResamplingMethod', 'BILINEAR_INTERPOLATION')
        terrain_parameters.put('imgResamplingMethod', 'BILINEAR_INTERPOLATION')
        terrain_parameters.put('mapProjection', 'WGS84(DD)')

        # apply the terrain correction
        terrain_corrected = GPF.createProduct('Terrain-Correction', terrain_parameters, product)

        # apply the speckle filter
        speckle_filtered = GPF.createProduct('Speckle-Filter', speckle_parameters, terrain_corrected)

        # write the terrain-corrected image to a file
        output_path = os.path.join('G:\\rcm\\output_rcm', file_name+'.tif')
        ProductIO.writeProduct(speckle_filtered, output_path, 'GeoTIFF-BigTIFF')

        print('finish')

if __name__=='__main__':
    # sar_tc_sn(file_path='E:\\tif_images_donnie_creek\\')
    upload_in_parallel(True, 'E:\\tif_images_donnie_creek\\')
    # upload_by_log()
