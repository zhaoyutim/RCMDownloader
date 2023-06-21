import glob
import multiprocessing
import os
import subprocess
import sys
sys.path.append('/Users/zhaoyu/.snap/snap-python')
from osgeo import gdal
from snappy import ProductIO, HashMap, GPF


def upload_to_gcloud(file):
    print('Upload to gcloud')
    file_name = file.split('/')[-1]
    id = file.split('/')[-2]
    upload_cmd = 'gsutil cp ' + file + ' gs://ai4wildfire/VNPPROJ5/'+id+'/' + file_name
    print(upload_cmd)
    os.system(upload_cmd)
    print('finish uploading' + file_name)


def upload_to_gee(file):
    print('start uploading to gee')
    file_name = file.split('/')[-1]
    id = file.split('/')[-2]
    date = file_name[6:16]
    time = file.split('/')[-1][17:21]
    time_start = date + 'T' + time[:2] + ':' + time[2:] + ':00'
    cmd = 'earthengine upload image --time_start ' + time_start + ' --asset_id=projects/proj5-dataset/assets/proj5_dataset/' + \
          id+'_'+file_name[:-4] + ' --pyramiding_policy=sample gs://ai4wildfire/VNPPROJ5/'+id+'/' + file_name
    print(cmd)
    subprocess.call(cmd.split())
    print('Uploading in progress for image ' + time_start)

def upload(file):
    upload_to_gcloud(file)
    upload_to_gee(file)

def upload_in_parallel(import_all=True, filepath='data/subset'):
    if import_all:
        file_list = glob.glob(os.path.join(filepath, 'CANADA', '*.tif'))
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
            id = file.split('/')[-2]
            date = file.split('/')[-1][6:16]
            time = file.split('/')[-1][17:21]
            vnp_json = open(glob.glob(os.path.join('data/VNPL1', id, date, 'D', '*.json'))[0], 'rb')
            import json
            def get_name(json):
                return json.get('name').split('.')[2]
            vnp_time = list(map(get_name, json.load(vnp_json)['content']))
            if time not in vnp_time or 'IMG' not in file:
                continue
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

def sar_tc_sn():


    # load the Sentinel-1 image
    product = ProductIO.readProduct('/Users/zhaoyu/PycharmProjects/eodms-cli/data/RCM1_OK2388975_PK2567859_1_SC30MCPA_20230523_011049_CH_CV_MLC.zip')

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
    ProductIO.writeProduct(speckle_filtered, 'output.tif', 'GeoTIFF-BigTIFF')

    print('finish')

if __name__=='__main__':
    sar_tc_sn()
    # upload_in_parallel(True, 'data/*/imagery')
    # upload_by_log()
