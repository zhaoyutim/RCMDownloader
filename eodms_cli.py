##############################################################################
# MIT License
# 
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2023
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.
# 
##############################################################################

__title__ = 'EODMS-CLI'
__author__ = 'Kevin Ballantyne'
__copyright__ = 'Copyright (c) His Majesty the King in Right of Canada, ' \
                'as represented by the Minister of Natural Resources, 2023'
__license__ = 'MIT License'
__description__ = 'Script used to search, order and download imagery from ' \
                  'the EODMS using the REST API (RAPI) service.'
__version__ = '3.2.2'
__maintainer__ = 'Kevin Ballantyne'
__email__ = 'eodms-sgdot@nrcan-rncan.gc.ca'

import datetime
import logging
import logging.handlers as handlers
import os
import pathlib
import sys
import traceback

import click
import eodms_rapi
from packaging import version as pack_v

from Prompter import Prompter
from scripts import config_util
from scripts import utils as eod_util

proc_choices = {'full': {
                    'name': 'Search, order and/or download',
                    'desc': 'Search, order and/or download images using an AOI '
                            'and/or filters'
                },
                'order_csv': {
                    'name': 'EODMS UI Ordering',
                    'desc': 'Order & download images using EODMS UI search '
                            'results (CSV file)'
                },
                'record_id': {
                    'name': 'Record IDs',
                    'desc': 'Order and download a single or set of images '
                            'using Record IDs'
                },
                'download_available': {
                    'name': 'Download Available Order Items',
                    'desc': 'Downloads order items with status '
                            'AVAILABLE_FOR_DOWNLOAD'
                },
                'download_results': {
                    'name': 'Download EODMS-CLI Results',
                    'desc': 'Download existing orders using a CSV file from '
                            'a previous order/download process (files found '
                            'under "results" folder)'
                }
            }

eodmsrapi_recent = '1.4.5'
#------------------------------------------------------------------------------

output_help = '''The output file path containing the results in a
                             geospatial format.
 The output parameter can be:
 - None (empty): No output will be created (a results CSV file will still be
     created in the 'results' folder)
 - GeoJSON: The output will be in the GeoJSON format
     (use extension .geojson or .json)
 - KML: The output will be in KML format (use extension .kml) (requires GDAL 
        Python package)
 - GML: The output will be in GML format (use extension .gml) (requires GDAL 
        Python package)
 - Shapefile: The output will be ESRI Shapefile (requires GDAL Python package)
     (use extension .shp)'''

abs_path = os.path.abspath(__file__)

def get_configuration_values(config_util, download_path):

    config_params = {}

    # Set the various paths
    if download_path is None or download_path == '':
        # download_path = config_info.get('Script', 'downloads')
        download_path = config_util.get('Paths', 'downloads')

        if download_path == '':
            download_path = os.path.join(os.path.dirname(abs_path),
                                         'downloads')
        elif not os.path.isabs(download_path):
            download_path = os.path.join(os.path.dirname(abs_path),
                                         download_path)
    config_params['download_path'] = download_path

    res_path = config_util.get('Paths', 'results')
    if res_path == '':
        res_path = os.path.join(os.path.dirname(abs_path), 'results')
    elif not os.path.isabs(res_path):
        res_path = os.path.join(os.path.dirname(abs_path),
                                res_path)
    config_params['res_path'] = res_path

    log_path = config_util.get('Paths', 'log')
    if log_path == '':
        log_path = os.path.join(os.path.dirname(abs_path), 'log',
                               'logger.log')
    elif not os.path.isabs(log_path):
        log_path = os.path.join(os.path.dirname(abs_path),
                               log_path)
    config_params['log_path'] = log_path

    # Set the timeout values
    timeout_query = config_util.get('RAPI', 'timeout_query')
    # timeout_order = config_info.get('Script', 'timeout_order')
    timeout_order = config_util.get('RAPI', 'timeout_order')

    try:
        timeout_query = float(timeout_query)
    except ValueError:
        timeout_query = 60.0

    try:
        timeout_order = float(timeout_order)
    except ValueError:
        timeout_order = 180.0
    config_params['timeout_query'] = timeout_query
    config_params['timeout_order'] = timeout_order

    config_params['keep_results'] = config_util.get('Script', 'keep_results')
    config_params['keep_downloads'] = config_util.get('Script',
                                                      'keep_downloads')

    # Get the total number of results per query
    config_params['max_results'] = config_util.get('RAPI', 'max_results')

    # Get the minimum date value to check orders
    config_params['order_check_date'] = config_util.get('RAPI',
                                                        'order_check_date')

    config_params['download_attempts'] = config_util.get('RAPI',
                                                        'download_attempts')

    # Get URL for debug purposes
    config_params['rapi_url'] = config_util.get('Debug', 'root_url')

    return config_params

def print_support(err_str=None):
    """
    Prints the 2 different support message depending if an error occurred.
    
    :param err_str: The error string to print along with support.
    :type  err_str: str
    """

    eod_util.EodmsProcess().print_support(True, err_str)


@click.command(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--configure', default=None,
              help='Runs the configuration setup allowing the user to enter '
                   'configuration values.')
@click.option('--username', '-u', default=None,
              help='The username of the EODMS account used for '
                   'authentication.')
@click.option('--password', '-p', default=None,
              help='The password of the EODMS account used for '
                   'authentication.')
@click.option('--process', '-prc', '-r', default=None,
              help='The type of process to run from this list of '
                   'options:\n- %s'
                   % '\n- '.join(["%s: %s" % (k, v)
                                  for k, v in proc_choices.items()]))
@click.option('--input_val', '-i', default=None,
              help='An input file (can either be an AOI, a CSV file '
                   'exported from the EODMS UI), a WKT feature or a set '
                   'of Record IDs. Valid AOI formats are GeoJSON, KML or '
                   'Shapefile (Shapefile requires the GDAL Python '
                   'package).')
@click.option('--collections', '-c', default=None,
              help='The collection of the images being ordered (separate '
                   'multiple collections with a comma).')
@click.option('--filters', '-f', default=None,
              help='A list of filters for a specific collection.')
@click.option('--dates', '-d', default=None,
              help='The date ranges for the search.')
@click.option('--maximum', '-max', '-m', default=None,
              help='For Process 1 & 2, the maximum number of images to order '
                   'and download and the maximum number of images per order, '
                   'separated by a colon. If no_order is set to True, this '
                   'parameter will set the maximum images for which to search. '
                   'For Process 4, a single value to specify the maximum '
                   'number of images with status AVAILABLE_FOR_DOWNLOAD '
                   'to download.')
@click.option('--priority', '-pri', '-l', default=None,
              help='The priority level of the order.\nOne of "Low", '
                   '"Medium", "High" or "Urgent" (default "Medium").')
@click.option('--output', '-o', default=None, help=output_help)
# @click.option('--csv_fields', '-cf', default=None,
#               help='The fields in the input CSV file used to get images.')
@click.option('--aws', '-a', is_flag=True, default=None,
              help='Determines whether to download from AWS (only applies '
                   'to Radarsat-1 imagery).')
@click.option('--overlap', '-ov', default=None,
              help='The minimum percentage of overlap between AOI and images '
                   '(if no AOI specified, this parameter is ignored).')
@click.option('--orderitems', '-oid', default=None,
              help="For Process 4, a set of Order IDs and/or Order Item IDs. "
                   "This example specifies Order IDs and Order Item IDs: "
                   "'order:151873,151872|item:1706113,1706111'")
@click.option('--no_order', '-nord', is_flag=True, default=None,
              help='If set, no ordering and downloading will occur.')
@click.option('--downloads', '-dn', default=None,
              help='The path where the images will be downloaded. Overrides '
                   'the downloads parameter in the configuration file.')
@click.option('--silent', '-s', is_flag=True, default=None,
              help='Sets process to silent which suppresses all questions.')
@click.option('--version', '-v', is_flag=True, default=None,
              help='Prints the version of the script.')
def cli(username, password, input_val, collections, process, filters, dates,
        maximum, priority, output, aws, overlap, orderitems, no_order,
        downloads, silent, version, configure):
    """
    Search & Order EODMS products.
    """

    os.system("title " + __title__)
    sys.stdout.write("\x1b]2;%s\x07" % __title__)

    python_version_cur = ".".join([str(sys.version_info.major),
                                   str(sys.version_info.minor),
                                   str(sys.version_info.micro)])
    # if StrictVersion(python_version_cur) < StrictVersion('3.6'):
    if pack_v.Version(python_version_cur) < pack_v.Version('3.6'):
        raise Exception("Must be using Python 3.6 or higher")

    if '-v' in sys.argv or '--v' in sys.argv or '--version' in sys.argv:
        print(f"\n  {__title__}, version {__version__}\n")
        sys.exit()

    conf_util = config_util.ConfigUtils()

    if configure:
        conf_util.ask_user(configure)
        # print("You've entered configuration mode.")
        sys.exit()

    print("\n##########################################################"
          "#######################")
    print(f"#                              {__title__} v{__version__}         "
          f"                        #")
    print("############################################################"
          "#####################")

    if pack_v.Version(eodms_rapi.__version__) < \
            pack_v.Version(eodmsrapi_recent):
        err_msg = "The py-eodms-rapi currently installed is an older " \
                  "version. Please install the latest version using " \
                  "'pip install py-eodms-rapi -U'."
        eod_util.EodmsProcess().print_support(True, err_msg)
        sys.exit(1)


    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

    eod = None
    logger = None

    try:

        params = {'username': username,
                  'password': password,
                  'input_val': input_val,
                  'collections': collections,
                  'process': process,
                  'filters': filters,
                  'dates': dates,
                  'maximum': maximum,
                  'priority': priority,
                  'output': output,
                  # 'csv_fields': csv_fields,
                  'aws': aws,
                  'overlap': overlap,
                  'orderitems': orderitems,
                  'no_order': no_order,
                  'downloads': downloads,
                  'silent': silent,
                  'version': version}

        # Set all the parameters from the config.ini file
        # config_info = get_config()
        conf_util.import_config()

        config_params = get_configuration_values(conf_util, downloads)
        download_path = config_params['download_path']
        res_path = config_params['res_path']
        log_path = config_params['log_path']
        timeout_query = config_params['timeout_query']
        timeout_order = config_params['timeout_order']
        keep_results = config_params['keep_results']
        keep_downloads = config_params['keep_downloads']
        max_results = config_params['max_results']
        order_check_date = config_params['order_check_date']
        download_attempts = config_params['download_attempts']
        rapi_url = config_params['rapi_url']

        print(f"\nImages will be downloaded to '{download_path}'.")

        # Setup logging
        logger = logging.getLogger('EODMSRAPI')

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - '
                                      '%(message)s',
                                      datefmt='%Y-%m-%d %I:%M:%S %p')

        if not os.path.exists(os.path.dirname(log_path)):
            pathlib.Path(os.path.dirname(log_path)).mkdir(
                parents=True, exist_ok=True)

        log_handler = handlers.RotatingFileHandler(log_path,
                                                   maxBytes=500000,
                                                   backupCount=2)
        log_handler.setLevel(logging.DEBUG)
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        logger.info(f"Script start time: {start_str}")

        eod = eod_util.EodmsProcess(download=download_path,
                                    results=res_path, log=log_path,
                                    timeout_order=timeout_order,
                                    timeout_query=timeout_query,
                                    max_res=max_results,
                                    keep_results=keep_results,
                                    keep_downloads=keep_downloads,
                                    order_check_date=order_check_date,
                                    download_attempts=download_attempts,
                                    rapi_url=rapi_url)

        print(f"\nCSV Results will be placed in '{eod.results_path}'.")

        eod.cleanup_folders()

        #########################################
        # Get authentication if not specified
        #########################################

        prmpt = Prompter(eod, conf_util, params, click)

        prmpt.prompt()

        print("\nProcess complete.")

        eod.print_support()

    except KeyboardInterrupt:
        msg = "Process ended by user."
        print(f"\n{msg}")

        if 'eod' in vars() or 'eod' in globals():
            eod.print_support()
            eod.export_results()
        else:
            eod_util.EodmsProcess().print_support()
        logger.info(msg)
        sys.exit(1)
    except Exception:
        trc_back = f"\n{traceback.format_exc()}"
        # print(f"trc_back: {trc_back}")
        if 'eod' in vars() or 'eod' in globals():
            eod.print_support(True, trc_back)
            eod.export_results()
        else:
            eod_util.EodmsProcess().print_support(True, trc_back)
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    sys.exit(cli())
