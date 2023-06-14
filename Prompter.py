import base64
import binascii
import getpass
import logging
import os
import re
import sys
import click
from scripts import utils as eod_util
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

class Prompter:
    """
    Class used to prompt the user for all inputs.
    """

    def __init__(self, eod, config_util, params, in_click, testing=False):
        """
        Initializer for the Prompter class.

        :param eod: The Eodms_OrderDownload object.
        :type  eod: self.Eodms_OrderDownload
        :param config_util: The ConfigUtils object
        :type  config_util: ConfigUtils
        :param params: An empty dictionary of parameters.
        :type  params: dict
        """

        self.eod = eod
        self.config_util = config_util
        self.config_info = config_util.get_info()
        self.params = params
        self.click = in_click
        self.process = None
        self.testing = testing

        self.logger = logging.getLogger('eodms')

    # def remove_accents(self, s):
    #     nkfd_form = unicodedata.normalize('NFKD', s)
    #     return u''.join([c for c in nkfd_form
    #     if not unicodedata.combining(c)])

    def ask_aoi(self, input_fn):
        """
        Asks the user for the geospatial input filename.

        :param input_fn: The geospatial input filename if already set by the
                command-line.
        :type  input_fn: str

        :return: The geospatial filename entered by the user.
        :rtype: str
        """

        if input_fn is None or input_fn == '':

            # if self.eod.silent:
            #     err_msg = "No AOI file or feature specified. Exiting process."
            #     self.eod.print_support(err_msg)
            #     self.logger.error(err_msg)
            #     sys.exit(1)

            if not self.eod.silent:
                print(
                    "\n--------------Enter Input Geospatial File or Feature----"
                    "----------")

                msg = "Enter the full path name of a GML, KML, Shapefile or " \
                      "GeoJSON containing an AOI or a WKT feature to " \
                      "restrict the search to a specific location\n"
                err_msg = "No AOI or feature specified. Please enter a WKT " \
                          "feature or a valid GML, KML, Shapefile or GeoJSON " \
                          "file"
                input_fn = self.get_input(msg, err_msg, required=False)

        if input_fn is None or input_fn == '':
            return None

        if os.path.exists(input_fn):
            if input_fn.find('.shp') > -1:
                try:
                    import osgeo.ogr as ogr
                    import osgeo.osr as osr
                    # GDAL_INCLUDED = True
                except ImportError:
                    try:
                        import ogr
                        import osr
                        # GDAL_INCLUDED = True
                    except ImportError:
                        err_msg = "Cannot open a Shapefile without GDAL. " \
                                  "Please install the GDAL Python package if " \
                                  "you'd like to use a Shapefile for your AOI."
                        self.logger.warning(err_msg)
                        return None

            input_fn = input_fn.strip()
            input_fn = input_fn.strip("'")
            input_fn = input_fn.strip('"')

            # ---------------------------------
            # Check validity of the input file
            # ---------------------------------

            input_fn = self.eod.validate_file(input_fn, True)

            if not input_fn:
                return None

        elif any(s in input_fn for s in self.eod.aoi_extensions):
            err_msg = f"Input file {os.path.abspath(input_fn)} does not exist."
            # self.eod.print_support(err_msg)
            self.logger.warning(err_msg)
            return None

        else:
            if not self.eod.eodms_geo.is_wkt(input_fn):
                err_msg = "Input feature is not a valid WKT."
                # self.eod.print_support(err_msg)
                self.logger.warning(err_msg)
                return None

        return input_fn

    def ask_aws(self, aws):
        """
        Asks the user if they'd like to download the image using AWS,
            if applicable.

        :param aws: If already entered by the command-line, True if the user
                    wishes to download from AWS.
        :type  aws: boolean

        :return: True if the user wishes to download from AWS.
        :rtype: boolean
        """

        if not aws:

            if not self.eod.silent:
                print("\n--------------Download from AWS?--------------")

                print("\nSome Radarsat-1 images contain direct download "
                      "links to GeoTIFF files in an Open Data AWS "
                      "Repository.")

                msg = "For images that have an AWS link, would you like to " \
                      "download the GeoTIFFs from the repository instead of " \
                      "submitting an order to the EODMS?\n"
                aws = self.get_input(msg, required=False, options=['Yes', 'No'])

                if aws.lower().find('y') > -1:
                    aws = True
                else:
                    aws = False

        return aws

    def ask_collection(self, coll, coll_lst=None):
        """
        Asks the user for the collection(s).

        :param coll: The collections if already set by the command-line.
        :type  coll: str
        :param coll_lst: A list of collections retrieved from the RAPI.
        :type  coll_lst: list

        :return: A list of collections entered by the user.
        :rtype: list
        """

        if coll is None:

            if coll_lst is None:
                coll_lst = self.eod.eodms_rapi.get_collections(True, opt='both')

            if self.eod.silent:
                err_msg = "No collection specified. Exiting process."
                self.eod.print_support(True, err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

            # print(dir(coll_lst))

            # print("coll_lst: %s" % coll_lst)

            print("\n--------------Enter Collection--------------")

            # List available collections for this user
            print("\nAvailable Collections:\n")
            # print(f"coll_lst: {coll_lst}")
            coll_lst = sorted(coll_lst, key=lambda x: x['title'])
            # coll_lst.sort()
            for idx, c in enumerate(coll_lst):
                msg = f"{idx + 1}. {c['title']} ({c['id']})"
                # if c['id'] == 'NAPL':
                #     msg += ' (open data only)'
                print(msg)

            # Prompted user for number(s) from list
            msg = "Enter the number of a collection from the list " \
                  "above (for multiple collections, enter each number " \
                  "separated with a comma)"
            err_msg = "At least one collection must be specified."
            in_coll = self.get_input(msg, err_msg)

            # Convert number(s) to collection name(s)
            coll_vals = in_coll.split(',')

            # ---------------------------------------
            # Check validity of the collection entry
            # ---------------------------------------

            check = self.eod.validate_int(coll_vals, len(coll_lst))
            if not check:
                err_msg = "A valid Collection must be specified. " \
                          "Exiting process."
                self.eod.print_support(True, err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

            coll = [coll_lst[int(i) - 1]['id'] for i in coll_vals
                    if i.isdigit()]
        else:
            coll = coll.split(',')

        # ------------------------------
        # Check validity of Collections
        # ------------------------------
        for c in coll:
            check = self.eod.validate_collection(c)
            if not check:
                err_msg = f"Collection '{c}'' is not valid."
                self.eod.print_support(True, err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

        return coll

    def ask_dates(self, dates):
        """
        Asks the user for dates.

        :param dates: The dates if already set by the command-line.
        :type  dates: str

        :return: The dates entered by the user.
        :rtype: str
        """

        # Get the date range
        if dates is None:

            if not self.eod.silent:
                print("\n--------------Enter Date Range--------------")

                msg = "Enter a date range (ex: 20200525-20200630T200950) " \
                      "or a previous time-frame (24 hours) " \
                      "(leave blank to search all years)\n"
                dates = self.get_input(msg, required=False)

        # -------------------------------
        # Check validity of filter input
        # -------------------------------
        if dates is not None and not dates == '':
            dates = self.eod.validate_dates(dates)

            if not dates:
                err_msg = "The dates entered are invalid. "
                self.eod.print_support(True, err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

        return dates

    def ask_fields(self, csv_fields, fields):

        if csv_fields is not None:
            return csv_fields.split(',')

        srch_fields = []
        for f in fields:
            if f.lower() in self.eod.csv_unique:
                srch_fields.append(f.lower())

        if len(srch_fields) > 0:
            return srch_fields

        if not self.eod.silent:
            print("\n--------------Enter CSV Unique Fields--------------")

            print("\nAvailable fields in the CSV file:")
            for f in fields:
                print(f"  {f}")

            msg = "Enter the fields from the CSV file which can be used to " \
                  "determine the images (separate each with a comma)"
            # err_msg = "At least one collection must be specified."
            input_fields = self.get_input(msg)  # , err_msg)

            srch_fields = [f.strip() for f in input_fields.split(',')]

            return srch_fields

    def ask_filter(self, filters):
        """
        Asks the user for the search filters.

        :param filters: The filters if already set by the command-line.
        :type  filters: str

        :return: A dictionary containing the filters entered by the user.
        :rtype: dict
        """

        if filters is None:
            filt_dict = {}

            if not self.eod.silent:

                print("\n--------------Enter Filters--------------")

                # Ask for the filters for the given collection(s)
                for coll in self.params['collections']:
                    coll_id = self.eod.get_full_collid(coll)

                    coll_fields = self.eod.field_mapper.get_fields(coll_id)

                    if coll_id in self.eod.field_mapper.get_colls():
                        # field_map = self.eod.get_fieldMap()[coll_id]

                        print(f"\nAvailable fields for '{coll}':")
                        for f in coll_fields.get_eod_fieldnames():
                            print(f"  {f}")

                        print("NOTE: Filters must be entered in the format "
                              "of <field_id>=<value>|<value>|... (field "
                              "IDs are not case sensitive); separate each "
                              "filter with a comma. To see a list "
                              "of field choices, enter '? <field_id>'.")

                        msg = "Enter the filters you would like to apply " \
                              "to the search"

                        filt_items = '?'

                        while filt_items.find('?') > -1:
                            filt_items = input(f"\n->> {msg}:\n")

                            if filt_items.find('?') > -1:
                                field_val = filt_items.replace('?', '').strip()

                                field_obj = coll_fields.get_field(field_val)
                                field_title = field_obj.get_rapi_field_title()

                                if field_title is None:
                                    print("Not a valid field.")
                                    continue

                                field_choices = self.eod.eodms_rapi. \
                                    get_fieldChoices(coll_id, field_title)

                                if isinstance(field_choices, dict):
                                    field_choices = f'any %s value' % \
                                                    field_choices['data_type']
                                else:
                                    field_choices = ', '.join(field_choices)

                                print(f"\nAvailable choices for "
                                      f"'{field_val}': {field_choices}")

                        if filt_items == '':
                            filt_dict[coll_id] = []
                        else:

                            # -------------------------------
                            # Check validity of filter input
                            # -------------------------------
                            filt_items = self.eod.validate_filters(filt_items,
                                                                   coll_id)

                            if not filt_items:
                                sys.exit(1)

                            filt_items = filt_items.split(',')
                            # In case the user put collections in filters
                            filt_items = [f.split('.')[1]
                                          if f.find('.') > -1
                                          else f for f in filt_items]
                            filt_dict[coll_id] = filt_items

        else:
            # User specified in command-line

            # Possible formats:
            #   1. Only one collection: <field_id>=<value>|<value>,
            #       <field_id>=<value>&<value>,...
            #   2. Multiple collections but only specifying one set of filters:
            #       <coll_id>.<field_id>=<value>|<value>,...
            #   3. Multiple collections with filters:
            #       <coll_id>.<field_id>=<value>,...
            #       <coll_id>.<field_id>=<value>,...

            filt_dict = {}

            for coll in self.params['collections']:
                # Split filters by comma
                filt_lst = filters.split(',')
                for f in filt_lst:
                    f = f.strip('"')
                    if f == '':
                        continue
                    if f.find('.') > -1:
                        coll, filt_items = f.split('.')
                        filt_items = self.eod.validate_filters(filt_items,
                                                               coll)
                        if not filt_items:
                            sys.exit(1)
                        coll_id = self.eod.get_full_collid(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict.get(coll_id)
                        else:
                            coll_filters = []
                        coll_filters.append(
                            filt_items.replace('"', '').replace("'", ''))
                        filt_dict[coll_id] = coll_filters
                    else:
                        coll_id = self.eod.get_collid_by_name(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
                        else:
                            coll_filters = []
                        coll_filters.append(f)
                        filt_dict[coll_id] = coll_filters

        return filt_dict

    def ask_input_file(self, input_fn, msg):
        """
        Asks the user for the input filename.

        :param input_fn: The input filename if already set by the command-line.
        :type  input_fn: str
        :param msg: The message used to ask the user.
        :type  msg: str

        :return: The input filename.
        :rtype: str
        """

        if input_fn is None or input_fn == '':

            if self.eod.silent:
                err_msg = "No CSV file specified. Exiting process."
                self.eod.print_support(True, err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

            print("\n--------------Enter Input CSV File--------------")

            err_msg = "No CSV specified. Please enter a valid CSV file"
            input_fn = self.get_input(msg, err_msg)

        if not os.path.exists(input_fn):
            # err_msg = "Not a valid CSV file. Please enter a valid CSV file."
            err_msg = "The specified CSV file does not exist. Please enter a " \
                      "valid CSV file."
            self.eod.print_support(True, err_msg)
            self.logger.error(err_msg)
            sys.exit(1)

        return input_fn

    def ask_maximum(self, maximum, max_type='order'):
        """
        Asks the user for maximum number of order items and the number of
            items per order.

        :param maximum: The maximum if already set by the command-line.
        :type  maximum: str
        :param max_type: The type of maximum to set ('order' or 'download').
        :type  max_type: str
        :param no_order: Determines whether the maximum is for searching or
        ordering.
        :type  no_order: boolean

        :return: If max_type is 'order', the maximum number of order items
        and/or number of items per order, separated by ':'. If max_type is
        'download', a single number specifying how many images to download.
        :rtype: str
        """

        # Get the no_order value
        no_order = self.params.get('no_order')

        if maximum is None or maximum == '':

            if not self.eod.silent:
                if no_order:
                    print("\n--------------Enter Maximum Search Results------"
                          "------")
                    msg = "Enter the maximum number of images you would " \
                          "like to search for (leave blank to search for all " \
                          "images)"

                    maximum = self.get_input(msg, required=False)

                    return maximum

                if max_type == 'download':
                    print("\n--------------Enter Maximum for Downloads--------"
                          "------")
                    msg = "Enter the number of images with status " \
                          "AVAILABLE_FOR_DOWNLOAD you would like to " \
                          "download (leave blank to download all images " \
                          "with this status)"

                    maximum = self.get_input(msg, required=False)

                    return maximum
                else:
                    if not self.process == 'order_csv':

                        print("\n--------------Enter Maximums for Ordering------------"
                              "--")

                        msg = "Enter the total number of images you'd " \
                              "like to order (leave blank for no limit)"

                        total_records = self.get_input(msg, required=False)

                        # ------------------------------------------
                        # Check validity of the total_records entry
                        # ------------------------------------------

                        if total_records == '':
                            total_records = None
                        else:
                            total_records = self.eod.validate_int(total_records)
                            if not total_records:
                                self.eod.print_msg("WARNING: Total "
                                                   "number of images "
                                                   "value not valid. "
                                                   "Excluding it.",
                                                   indent=False)
                                total_records = None
                            else:
                                total_records = str(total_records)
                    else:
                        total_records = None

                    msg = "If you'd like a limit of images per order, " \
                          "enter a value (EODMS sets a maximum limit of " \
                          "100)"

                    order_limit = self.get_input(msg, required=False)

                    if order_limit == '':
                        order_limit = None
                    else:
                        order_limit = self.eod.validate_int(order_limit,
                                                            100)
                        if not order_limit:
                            self.eod.print_msg("WARNING: Order limit "
                                               "value not valid. "
                                               "Excluding it.",
                                               indent=False)
                            order_limit = None
                        else:
                            order_limit = str(order_limit)

                    maximum = ':'.join(filter(None, [total_records,
                                                     order_limit]))

        else:

            if max_type == 'order':
                if self.process == 'order_csv':

                    print("\n--------------Enter Images per Order------------"
                          "--")

                    if maximum.find(':') > -1:
                        total_records, order_limit = maximum.split(':')
                    else:
                        total_records = None
                        order_limit = maximum

                    maximum = ':'.join(filter(None, [total_records,
                                                     order_limit]))

        return maximum

    def ask_orderitems(self, orderitems):
        """
        Asks the user for a list Order IDs or Order Item IDs.

        :param orderitems

        """

        if orderitems is None:
            if not self.eod.silent:
                print("\n--------------Order/Order Item IDs--------------")

                msg = "\nEnter a list of Order IDs and/or Order Item IDs, " \
                      "separating each ID with a comma and separating Order " \
                      "IDs and Order Items with a vertical line " \
                      "(ex: 'orders:<order_id>,<order_id>|items:" \
                      "<order_item_id>,...') (leave blank to skip)\n"

                orderitems = self.get_input(msg, required=False)

        return orderitems

    def ask_order(self, no_order):
        """
        Asks the user if they would like to suppress ordering and downloading.

        :param no_order:
        :return:
        """

        if no_order is None:
            if not self.eod.silent:
                print("\n--------------Suppress Ordering--------------")

                msg = "\nWould you like to only search and not order?\n"
                no_order = self.get_input(msg, required=False,
                                          options=['yes', 'no'], default='n')

                if no_order.lower().find('y') > -1:
                    no_order = True
                else:
                    no_order = False

        return no_order

    def ask_output(self, output):
        """
        Asks the user for the output geospatial file.

        :param output: The output if already set by the command-line.
        :type  output: str

        :return: The output geospatial filename.
        :rtype: str
        """

        if output is None:

            if not self.eod.silent:
                print("\n--------------Enter Output Geospatial File-------"
                      "-------")

                msg = "\nEnter the path of the output geospatial file " \
                      "(can also be GeoJSON, KML, GML or Shapefile) " \
                      "(default is no output file)\n"
                output = self.get_input(msg, required=False)

        return output

    def ask_overlap(self, overlap):

        if overlap is None:

            if not self.eod.silent:
                print("\n--------------Enter Minimum Overlap Percentage----"
                      "----------")

                msg = "\nEnter the minimum percentage of overlap between " \
                      "images and the AOI\n"
                overlap = self.get_input(msg, required=False)

        return overlap

    def ask_priority(self, priority):
        """
        Asks the user for the order priority level

        :param priority: The priority if already set by the command-line.
        :type  priority: str

        :return: The priority level.
        :rtype: str
        """

        priorities = ['low', 'medium', 'high', 'urgent']

        if priority is None:
            if not self.eod.silent:
                print("\n--------------Enter Priority--------------")

                msg = "Enter the priority level for the order"

                priority = self.get_input(msg, required=False,
                                          options=priorities, default='medium')

        if priority is None or priority == '':
            priority = 'Medium'
        elif priority.lower() not in priorities:
            self.eod.print_msg("WARNING: Not a valid 'priority' entry. "
                               "Setting priority to 'Medium'.", indent=False)
            priority = 'Medium'

        return priority

    def ask_process(self):
        """
        Asks the user what process they would like to run.

        :return: The value the process the user has chosen.
        :rtype: str
        """

        if self.eod.silent:
            process = 'full'
        else:
            print("\n--------------Choose Process Option--------------")
            choice_strs = []
            # print(f"proc_choices.items(): {proc_choices.items()}")
            for idx, v in enumerate(proc_choices.items()):
                desc_str = re.sub(r'\s+', ' ', v[1]['desc'].replace('\n', ''))
                choice_strs.append(f"  {idx + 1}: ({v[0]}) {desc_str}")
            choices = '\n'.join(choice_strs)

            print(f"\nWhat would you like to do?\n\n{choices}\n")
            process = input("->> Please choose the type of process [1]: ")

            if self.testing:
                print(f"FOR TESTING - Process entered: {process}")

            if process == '':
                process = 'full'
            else:
                # Set process value and check its validity

                process = self.eod.validate_int(process)

                if not process:
                    err_msg = "Invalid value entered for the 'process' " \
                              "parameter."
                    self.eod.print_support(True, err_msg)
                    self.logger.error(err_msg)
                    sys.exit(1)

                if process > len(proc_choices.keys()):
                    err_msg = "Invalid value entered for the 'process' " \
                              "parameter."
                    self.eod.print_support(True, err_msg)
                    self.logger.error(err_msg)
                    sys.exit(1)
                else:
                    process = list(proc_choices.keys())[int(process) - 1]

        return process

    def ask_record_ids(self, ids):
        """
        Asks the user for a single or set of Record IDs.

        :param ids: A single or set of Record IDs with their collections.
        :type  ids: str
        """

        if ids is None or ids == '':

            if not self.eod.silent:
                print("\n--------------Enter Record ID(s)--------------")

                msg = "\nEnter a single or set of Record IDs. Include the " \
                      "Collection ID next to each ID separated by a " \
                      "colon. Separate each ID with a comma. " \
                      "(Ex: RCMImageProducts:7625368,NAPL:3736869)\n"
                ids = self.get_input(msg, required=False)

        return ids

    def build_syntax(self):
        """
        Builds the command-line syntax to print to the command prompt.

        :return: A string containing the command-line syntax for the script.
        :rtype: str
        """

        click_ctx = click.get_current_context(silent=True)

        flags = {}
        if click_ctx is None:
            return ''

        cmd_params = click_ctx.to_info_dict()['command']['params']
        for p in cmd_params:
            flags[p['name']] = p['opts']

        syntax_params = []
        for p, pv in self.params.items():
            if pv is None or pv == '':
                continue
            if p == 'session':
                continue
            if p == 'eodms_rapi':
                continue

            flag = flags[p][1]

            if isinstance(pv, list):
                if flag == '-d':
                    pv = '-'.join(['"%s"' % i if i.find(' ') > -1 else i
                                   for i in pv])
                else:
                    pv = ','.join(['"%s"' % i if i.find(' ') > -1 else i
                                   for i in pv])

            elif isinstance(pv, dict):

                if flag == '-f':
                    filt_lst = []
                    for k, v_lst in pv.items():
                        for v in v_lst:
                            if v is None or v == '':
                                continue
                            v = v.replace('"', '').replace("'", '')
                            filt_lst.append(f"{k}.{v}")
                    if len(filt_lst) == 0:
                        continue
                    pv = '"%s"' % ','.join(filt_lst)

            elif isinstance(pv, bool):
                if not pv:
                    continue
                else:
                    pv = ''
            else:
                if isinstance(pv, str) and pv.find(' ') > -1:
                    pv = f'"{pv}"'
                elif isinstance(pv, str) and pv.find('|') > -1:
                    pv = f'"{pv}"'

            syntax_params.append(f'{flag} {pv}')

        out_syntax = "python %s %s -s" % (os.path.realpath(__file__),
                                          ' '.join(syntax_params))

        return out_syntax

    def get_input(self, msg, err_msg=None, required=True, options=None,
                  default=None, password=False):
        """
        Gets an input from the user for an argument.

        :param msg: The message used to prompt the user.
        :type  msg: str
        :param err_msg: The message to print when the user enters an invalid
                input.
        :type  err_msg: str
        :param required: Determines if the argument is required.
        :type  required: boolean
        :param options: A list of available options for the user to choose from.
        :type  options: list
        :param default: The default value if the user just hits enter.
        :type  default: str
        :param password: Determines if the argument is for password entry.
        :type  password: boolean

        :return: The value entered by the user.
        :rtype: str
        """

        if password:
            # If the argument is for password entry, hide entry
            in_val = getpass.getpass(prompt=f'->> {msg}: ')
        else:
            opt_str = ''
            if options is not None:
                opt_str = ' (%s)' % '/'.join(options)

            def_str = ''
            if default is not None:
                def_str = f' [{default}]'

            output = f"\n->> {msg}{opt_str}{def_str}: "
            if msg.endswith('\n'):
                msg_strp = msg.strip('\n')
                output = f"\n->> {msg_strp}{opt_str}{def_str}:\n"
            try:
                in_val = input(output)
            except EOFError as error:
                # Output expected EOFErrors.
                self.logger.error(error)
                sys.exit(1)

        if required and in_val == '':
            eod_util.EodmsProcess().print_support(True, err_msg)
            self.logger.error(err_msg)
            sys.exit(1)

        if in_val == '' and default is not None and not default == '':
            in_val = default

        if self.testing:
            print(f"FOR TESTING - Value entered: {in_val}")

        return in_val

    def print_syntax(self):
        """
        Prints the command-line syntax for the script.
        """

        print("\nUse this command-line syntax to run the same parameters:")
        cli_syntax = self.build_syntax()
        print(cli_syntax)
        self.logger.info(f"Command-line Syntax: {cli_syntax}")

    def prompt(self):
        """
        Prompts the user for the input options.
        """

        username = self.params.get('username')
        password = self.params.get('password')
        input_val = self.params.get('input_val')
        collections = self.params.get('collections')
        process = self.params.get('process')
        filters = self.params.get('filters')
        dates = self.params.get('dates')
        maximum = self.params.get('maximum')
        priority = self.params.get('priority')
        output = self.params.get('output')
        # csv_fields = self.params.get('csv_fields')
        aws = self.params.get('aws')
        overlap = self.params.get('overlap')
        orderitems = self.params.get('orderitems')
        no_order = self.params.get('no_order')
        downloads = self.params.get('downloads')
        silent = self.params.get('silent')
        version = self.params.get('version')

        if version:
            print(f"{__title__}: Version {__version__}")
            sys.exit()

        self.eod.set_silence(silent)

        new_user = False
        new_pass = False

        if username is None or password is None:
            print("\n--------------Enter EODMS Credentials--------------")

        if username is None or username == '':

            username = self.config_util.get('Credentials', 'username')

            # print(f"username: {username}")

            if username == '':
                msg = "Enter the username for authentication"
                err_msg = "A username is required to order images."
                username = self.get_input(msg, err_msg)
                new_user = True
            else:
                print("\nUsing the username set in the 'config.ini' file...")

        if password is None or password == '':

            password = self.config_util.get('Credentials', 'password')

            if password == '':
                msg = 'Enter the password for authentication'
                err_msg = "A password is required to order images."
                password = self.get_input(msg, err_msg, password=True)
                new_pass = True
            else:
                try:
                    password = base64.b64decode(password).decode("utf-8")
                except binascii.Error as err:
                    password = base64.b64decode(password +
                                                "========").decode("utf-8")
                print("Using the password set in the 'config.ini' file...")

        if new_user or new_pass:
            suggestion = ''
            if self.eod.silent:
                suggestion = " (it is best to store the credentials if " \
                             "you'd like to run the script in silent mode)"

            answer = input(f"\n->> Would you like to store the credentials "
                           f"for a future session{suggestion}? (y/n):")
            if answer.lower().find('y') > -1:
                # self.config_info.set('Credentials', 'username', username)
                self.config_util.set('Credentials', 'username', username)
                pass_enc = base64.b64encode(password.encode("utf-8")).decode(
                    "utf-8")
                # self.config_info.set('Credentials', 'password', str(pass_enc))
                self.config_util.set('Credentials', 'password', str(pass_enc))

                self.config_util.write()

        # Set the RAPI URL from the config file (only for development of
        #   EODMS-CLI)
        rapi_url = self.config_util.get('Debug', 'rapi_url')
        # print(f"rapi_url: {rapi_url}")
        if rapi_url:
            if rapi_url.find('staging'):
                print("\n**** RUNNING IN STAGING ENVIRONMENT ****\n")
            self.eod.rapi_domain = rapi_url

        # Get number of attempts when querying the RAPI
        self.eod.set_attempts(self.config_util.get('RAPI', 'access_attempts'))

        self.eod.create_session(username, password)

        self.params = {'collections': collections,
                       'dates': dates,
                       'input_val': input_val,
                       'maximum': maximum,
                       'process': process,
                       'downloads': downloads}

        print()
        coll_dict = self.eod.eodms_rapi.get_collections(True, opt='both')

        # print(f"dir(coll_lst): {dir(coll_lst)}")
        # print(f"coll_lst.__class__: {coll_lst.__class__}")
        # print(f"coll_lst type: {type(coll_lst).__name__}")
        # print(f"{'get_msgs' in dir(coll_lst)}")

        self.eod.check_error(coll_dict)

        print("\n(For more information on the following prompts, please refer"
              " to the README file.)")

        #########################################
        # Get the type of process
        #########################################

        if process is None or process == '':
            self.process = self.ask_process()
        else:
            self.process = process

        proc_num = list(proc_choices.keys()).index(self.process) + 1
        print("\n%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
        print(f" Running Process "
              f"{proc_num}: "
              f"{proc_choices[self.process]['name']}")
        print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\n")

        if self.process == 'search_only':
            msg = "\nNOTE: The 'search_only' process is no longer available. " \
                  "In future, please use the flags '--no_order' or '-nord' " \
                  "to suppress ordering and downloading.\nScript will " \
                  "perform a search without ordering or downloading."
            # self.eod.print_support(msg)
            self.logger.warning(msg)
            self.process = 'full'
            no_order = True

        self.params['process'] = self.process

        if self.process == 'download_only':
            print("\nNOTE: The process 'download_only' is now named "
                  "'download_results'. Please update any command-line "
                  "syntaxes.")
            self.process = 'download_results'

        if self.process == 'full':

            self.logger.info("Searching, ordering and downloading images "
                             "using an AOI.")

            # Get the collection(s)
            coll = self.ask_collection(collections, coll_lst=coll_dict)
            self.params['collections'] = coll

            # If Radarsat-1, ask user if they want to download from AWS
            if 'Radarsat1' in coll:
                aws = self.ask_aws(aws)
                self.params['aws'] = aws

            # Get the AOI file
            inputs = self.ask_aoi(input_val)
            self.params['input_val'] = inputs

            # If an AOI is specified, ask for a minimum overlap percentage
            if inputs is not None:
                overlap = self.ask_overlap(overlap)
                self.params['overlap'] = overlap

            # Get the filter(s)
            filt_dict = self.ask_filter(filters)
            # print(f"filt_dict: {filt_dict}")
            self.params['filters'] = filt_dict

            # Get the date(s)
            dates = self.ask_dates(dates)
            self.params['dates'] = dates

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            # Get the maximum(s)
            maximum = self.ask_maximum(maximum)
            self.params['maximum'] = maximum

            if not no_order:
                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            self.eod.search_order_download(self.params)

        elif self.process == 'order_csv':

            self.logger.info("Ordering and downloading images using results "
                             "from a CSV file.")

            #########################################
            # Get the CSV file
            #########################################

            msg = "Enter the full path of the CSV file exported " \
                  "from the EODMS UI website"
            inputs = self.ask_input_file(input_val, msg)
            self.params['input_val'] = inputs

            # fields = self.eod.get_input_fields(inputs)
            # csv_fields = self.ask_fields(csv_fields, fields)
            # self.params['csv_fields'] = csv_fields

            # If Radarsat-1, ask user if they want to download from AWS
            if os.path.exists(inputs):
                lines = open(inputs, 'r').read()
                if lines.lower().find('radarsat-1') > -1:
                    aws = self.ask_aws(aws)
                    self.params['aws'] = aws

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            # Get the maximum(s)
            maximum = self.ask_maximum(maximum)
            self.params['maximum'] = maximum

            if not no_order:
                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the order_csv process
            self.eod.order_csv(self.params)

        elif self.process == 'download_results':
            # Download existing orders using CSV file from previous session

            self.logger.info("Downloading images using results from a CSV "
                             "file from a previous session.")

            # Get the CSV file
            msg = "Enter the full path of the CSV Results file from a " \
                  "previous session"
            inputs = self.ask_input_file(input_val, msg)
            self.params['input_val'] = inputs

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the download_only process
            self.eod.download_results(self.params)

        elif self.process == 'download_available':
            self.logger.info("Downloading existing order items with status"
                             "AVAILABLE_FOR_DOWNLOAD.")

            orderitems = self.ask_orderitems(orderitems)
            self.params['orderitems'] = orderitems

            if orderitems is None or orderitems == '':
                # Get the maximum(s)
                maximum = self.ask_maximum(maximum, 'download')
                self.params['maximum'] = maximum

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the download_available process
            self.eod.download_available(self.params)


        elif self.process == 'record_id':
            # Order and download a single or set of images using Record IDs

            self.logger.info("Ordering and downloading images using "
                             "Record IDs")

            inputs = self.ask_record_ids(input_val)
            self.params['input_val'] = inputs

            # If Radarsat-1, ask user if they want to download from AWS
            if 'Radarsat1' in inputs:
                aws = self.ask_aws(aws)
                self.params['aws'] = aws

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            if not no_order:
                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the order_csv process
            self.eod.order_ids(self.params)

        else:
            self.eod.print_support("That is not a valid process type.")
            self.logger.error("An invalid parameter was entered during "
                              "the prompt.")
            sys.exit(1)