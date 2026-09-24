from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    Blueprint,
    redirect,
    url_for,
    flash,
    make_response,
    send_file,
    Request,
    current_app,
    session
)

from datetime import datetime, date, timedelta

from xhtml2pdf import pisa
from io import BytesIO


import mysql.connector
from mysql.connector import Error
import mysql


import re
import json
import os
import pandas as pd
from datetime import datetime
from decimal import Decimal
from db_connection import get_db_connection, create_core_weapons_table, create_qm_stock_table, drop_coy_issuance_table, create_troops_table
from flask import flash
# from middleware import require_login, jwt, JWT_ALGO, JWT_SECRET



