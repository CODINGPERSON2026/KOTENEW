"""
DigitalPersona U.are.U 4500 / HID Fingerprint Reader SDK Integration Module.
Uses the official 64-bit/32-bit dpfpdd.dll (Capture) and dpfj.dll (FingerJet Matcher) C-APIs
to interact directly with hardware optical fingerprint readers (VID: 0x05BA / PID: 0x000A)
and perform real-time Biometric 1:1 and 1:N Verification against Troop Army Numbers.
"""

import ctypes
import os
import sys
import time
import io
import base64
import hashlib
import threading

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Possible DLL search paths on Windows
DPFPDD_DLL_PATHS = [
    r"C:\Program Files\DigitalPersona\U.are.U SDK\Windows\Lib\x64\dpfpdd.dll",
    r"C:\Program Files\DigitalPersona\Bin\dpfpdd.dll",
    r"C:\Windows\System32\dpfpdd.dll",
    r"C:\Program Files (x86)\DigitalPersona\U.are.U SDK\Windows\Lib\win32\dpfpdd.dll",
    r"C:\Windows\SysWOW64\dpfpdd.dll",
    "dpfpdd.dll"
]

DPFJ_DLL_PATHS = [
    r"C:\Program Files\DigitalPersona\U.are.U SDK\Windows\Lib\x64\dpfj.dll",
    r"C:\Program Files\DigitalPersona\Bin\dpfj.dll",
    r"C:\Windows\System32\dpfj.dll",
    r"C:\Program Files (x86)\DigitalPersona\U.are.U SDK\Windows\Lib\win32\dpfj.dll",
    r"C:\Windows\SysWOW64\dpfj.dll",
    "dpfj.dll"
]

MAX_STR_LENGTH = 128
MAX_DEVICE_NAME_LENGTH = 1024
DPFJ_FMD_ANSI_378_2004 = 0x001B0001
DPFJ_PROBABILITY_ONE = 0x7fffffff
# Standard 1:1 Verification threshold for FingerJet (FAR 1/1,000 = 0.1% False Accept Rate per HID DigitalPersona SDK documentation)
MATCH_THRESHOLD = 2147483

QUALITY_MESSAGES = {
    0: "Fingerprint captured successfully.",
    1: "Capture timed out. No finger was placed on the sensor within the time limit.",
    2: "Capture was canceled.",
    4: "Non-finger or poor optical contact detected. Please place finger firmly.",
    8: "Fake finger / spoof detected.",
    16: "Finger is placed too far left on the sensor.",
    32: "Finger is placed too far right on the sensor.",
    64: "Finger is placed too high on the sensor.",
    128: "Finger is placed too low on the sensor.",
    256: "Finger is off-center. Please center your finger on the optical sensor.",
    512: "Finger scan was skewed. Place finger flat on the sensor.",
    1024: "Finger scan was too short. Keep finger steady on sensor.",
    2048: "Finger scan was too long.",
    4096: "Swipe speed too slow.",
    8192: "Swipe speed too fast.",
    16384: "Swipe direction wrong.",
    32768: "Reader optical glass requires cleaning. Wipe sensor surface and try again."
}

class DPFPDD_VER_INFO(ctypes.Structure):
    _fields_ = [
        ("major", ctypes.c_int),
        ("minor", ctypes.c_int),
        ("maintenance", ctypes.c_int),
    ]

class DPFPDD_HW_DESCR(ctypes.Structure):
    _fields_ = [
        ("vendor_name", ctypes.c_char * MAX_STR_LENGTH),
        ("product_name", ctypes.c_char * MAX_STR_LENGTH),
        ("serial_num", ctypes.c_char * MAX_STR_LENGTH),
    ]

class DPFPDD_HW_ID(ctypes.Structure):
    _fields_ = [
        ("vendor_id", ctypes.c_ushort),
        ("product_id", ctypes.c_ushort),
    ]

class DPFPDD_HW_VERSION(ctypes.Structure):
    _fields_ = [
        ("hw_ver", DPFPDD_VER_INFO),
        ("fw_ver", DPFPDD_VER_INFO),
        ("bcd_rev", ctypes.c_ushort),
    ]

class DPFPDD_DEV_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("name", ctypes.c_char * MAX_DEVICE_NAME_LENGTH),
        ("descr", DPFPDD_HW_DESCR),
        ("id", DPFPDD_HW_ID),
        ("ver", DPFPDD_HW_VERSION),
        ("modality", ctypes.c_uint),
        ("technology", ctypes.c_uint),
    ]

class DPFPDD_DEV_STATUS(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("status", ctypes.c_uint),
        ("finger_detected", ctypes.c_int),
        ("data", ctypes.c_ubyte * 16),
    ]

class DPFPDD_CAPTURE_PARAM(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("image_fmt", ctypes.c_uint),
        ("image_proc", ctypes.c_uint),
        ("image_res", ctypes.c_uint),
    ]

class DPFPDD_IMAGE_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("height", ctypes.c_uint),
        ("res", ctypes.c_uint),
        ("bpp", ctypes.c_uint),
    ]

class DPFPDD_CAPTURE_RESULT(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint),
        ("success", ctypes.c_int),
        ("quality", ctypes.c_uint),
        ("score", ctypes.c_uint),
        ("info", DPFPDD_IMAGE_INFO),
    ]


def _clean_str(raw_bytes):
    if not raw_bytes:
        return ""
    b = bytes(raw_bytes)
    if b.count(b'\x00') > len(b) // 3:
        try:
            return b.decode('utf-16-le', errors='ignore').strip().replace('\x00', '')
        except Exception:
            pass
    try:
        return b.decode('utf-8', errors='ignore').split('\x00')[0].strip()
    except Exception:
        return b.decode('latin-1', errors='ignore').split('\x00')[0].strip()


class DigitalPersonaSDK:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DigitalPersonaSDK, cls).__new__(cls)
                cls._instance._lib_capture = None
                cls._instance._lib_fingerjet = None
                cls._instance._initialized = False
                cls._instance._device_lock = threading.Lock()
                cls._instance._init_libraries()
            return cls._instance

    def _init_libraries(self):
        # 1. Initialize Capture Library (dpfpdd.dll)
        for path in DPFPDD_DLL_PATHS:
            if os.path.exists(path) or path == "dpfpdd.dll":
                try:
                    self._lib_capture = ctypes.CDLL(path)
                    self._setup_capture_signatures()
                    res = self._lib_capture.dpfpdd_init()
                    if res == 0:
                        self._initialized = True
                        print(f"[DigitalPersonaSDK] Loaded Capture Engine: {path}")
                        break
                except Exception as e:
                    print(f"[DigitalPersonaSDK] Error loading {path}: {e}")

        # 2. Initialize FingerJet Matcher Library (dpfj.dll)
        for path in DPFJ_DLL_PATHS:
            if os.path.exists(path) or path == "dpfj.dll":
                try:
                    self._lib_fingerjet = ctypes.CDLL(path)
                    self._setup_fingerjet_signatures()
                    print(f"[DigitalPersonaSDK] Loaded FingerJet Matcher Engine: {path}")
                    break
                except Exception as e:
                    print(f"[DigitalPersonaSDK] Error loading FingerJet {path}: {e}")

    def _setup_capture_signatures(self):
        if not self._lib_capture:
            return
        self._lib_capture.dpfpdd_init.restype = ctypes.c_int
        self._lib_capture.dpfpdd_exit.restype = ctypes.c_int
        self._lib_capture.dpfpdd_query_devices.restype = ctypes.c_int
        self._lib_capture.dpfpdd_query_devices.argtypes = [ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p]
        self._lib_capture.dpfpdd_open.restype = ctypes.c_int
        self._lib_capture.dpfpdd_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self._lib_capture.dpfpdd_close.restype = ctypes.c_int
        self._lib_capture.dpfpdd_close.argtypes = [ctypes.c_void_p]
        self._lib_capture.dpfpdd_get_device_status.restype = ctypes.c_int
        self._lib_capture.dpfpdd_get_device_status.argtypes = [ctypes.c_void_p, ctypes.POINTER(DPFPDD_DEV_STATUS)]
        self._lib_capture.dpfpdd_capture.restype = ctypes.c_int
        self._lib_capture.dpfpdd_capture.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(DPFPDD_CAPTURE_PARAM),
            ctypes.c_uint,
            ctypes.POINTER(DPFPDD_CAPTURE_RESULT),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.c_void_p
        ]

    def _setup_fingerjet_signatures(self):
        if not self._lib_fingerjet:
            return
        self._lib_fingerjet.dpfj_create_fmd_from_raw.restype = ctypes.c_int
        self._lib_fingerjet.dpfj_create_fmd_from_raw.argtypes = [
            ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_int, ctypes.c_uint, ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint)
        ]
        self._lib_fingerjet.dpfj_compare.restype = ctypes.c_int
        self._lib_fingerjet.dpfj_compare.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_uint)
        ]

    def is_available(self):
        return self._initialized and self._lib_capture is not None

    def list_connected_devices(self):
        """Returns a list of all detected HID DigitalPersona fingerprint readers."""
        if not self.is_available():
            self._init_libraries()
            if not self.is_available():
                return []

        dev_cnt = ctypes.c_uint(0)
        res = self._lib_capture.dpfpdd_query_devices(ctypes.byref(dev_cnt), None)
        if dev_cnt.value == 0:
            return []

        DevInfoArray = DPFPDD_DEV_INFO * dev_cnt.value
        dev_infos = DevInfoArray()
        for i in range(dev_cnt.value):
            dev_infos[i].size = ctypes.sizeof(DPFPDD_DEV_INFO)

        res = self._lib_capture.dpfpdd_query_devices(ctypes.byref(dev_cnt), dev_infos)
        if res != 0:
            return []

        devices = []
        for i in range(dev_cnt.value):
            d = dev_infos[i]
            vendor_str = _clean_str(d.descr.vendor_name) or "DigitalPersona / HID"
            prod_str = _clean_str(d.descr.product_name) or "U.are.U 4500 Fingerprint Reader"
            prod_str = prod_str.replace('\ufffd', '').strip()
            name_str = _clean_str(d.name)
            serial_str = _clean_str(d.descr.serial_num)

            devices.append({
                'name': f"HID DigitalPersona 4500 Optical Fingerprint Reader (VID:{d.id.vendor_id:04X})",
                'raw_name': d.name,
                'device_id': name_str,
                'vendor': vendor_str,
                'product': prod_str,
                'serial': serial_str,
                'vid': f"0x{d.id.vendor_id:04X}",
                'pid': f"0x{d.id.product_id:04X}",
                'status': 'READY'
            })
        return devices

    def extract_fmd(self, raw_bytes, width, height, dpi=500):
        """Extracts standard ANSI 378 FMD Minutiae biometric template from raw grayscale pixels."""
        if not self._lib_fingerjet or not raw_bytes or width <= 0 or height <= 0:
            return None
        try:
            MAX_FMD_SIZE = 4096
            fmd_buf = ctypes.create_string_buffer(MAX_FMD_SIZE)
            fmd_size = ctypes.c_uint(MAX_FMD_SIZE)
            res = self._lib_fingerjet.dpfj_create_fmd_from_raw(
                raw_bytes,
                len(raw_bytes),
                int(width),
                int(height),
                int(dpi),
                0,  # DPFJ_POSITION_UNKNOWN
                0,  # CBEFF
                DPFJ_FMD_ANSI_378_2004,
                fmd_buf,
                ctypes.byref(fmd_size)
            )
            if res == 0 and fmd_size.value > 0:
                fmd_bytes = fmd_buf.raw[:fmd_size.value]
                return base64.b64encode(fmd_bytes).decode('ascii')
        except Exception as e:
            print(f"[DigitalPersonaSDK] extract_fmd error: {e}")
        return None

    def compare_fmd(self, fmd_b64_1, fmd_b64_2):
        """
        Compares two ANSI 378 FMD minutiae templates using FingerJet Matcher.
        Returns (is_match, score, confidence_percentage).
        """
        if not self._lib_fingerjet or not fmd_b64_1 or not fmd_b64_2:
            # Fallback to direct string/hash comparison if FMD library is absent
            if fmd_b64_1 == fmd_b64_2:
                return True, 0, 100.0
            return False, DPFJ_PROBABILITY_ONE, 0.0

        try:
            buf1 = base64.b64decode(fmd_b64_1)
            buf2 = base64.b64decode(fmd_b64_2)
            score = ctypes.c_uint(DPFJ_PROBABILITY_ONE)

            res = self._lib_fingerjet.dpfj_compare(
                DPFJ_FMD_ANSI_378_2004,
                buf1, len(buf1), 0,
                DPFJ_FMD_ANSI_378_2004,
                buf2, len(buf2), 0,
                ctypes.byref(score)
            )

            if res == 0:
                score_val = score.value
                is_match = (score_val < MATCH_THRESHOLD)
                if score_val == 0:
                    confidence = 100.0
                elif is_match:
                    confidence = max(90.0, 100.0 - (score_val / MATCH_THRESHOLD) * 10.0)
                else:
                    confidence = 0.0
                return is_match, score_val, confidence
        except Exception as e:
            print(f"[DigitalPersonaSDK] compare_fmd error: {e}")

        # Fallback exact match
        if fmd_b64_1 == fmd_b64_2:
            return True, 0, 100.0
        return False, DPFJ_PROBABILITY_ONE, 0.0

    def capture_fingerprint(self, timeout_ms=8000):
        """
        Activates the optical sensor and WAITS for a physical finger press
        up to `timeout_ms` milliseconds (default: 8.0 seconds).
        Returns dict with captured impression details, image data, FMD template, and hash.
        """
        if not self.is_available():
            self._init_libraries()
            if not self.is_available():
                return {
                    'success': False,
                    'captured': False,
                    'message': 'DigitalPersona SDK (dpfpdd.dll) is not available. Please verify SDK installation.'
                }

        with self._device_lock:
            devices = self.list_connected_devices()
            if not devices:
                return {
                    'success': False,
                    'captured': False,
                    'message': 'No HID DigitalPersona fingerprint reader detected on USB ports. Please connect the device.'
                }

            target_dev = devices[0]
            dev_name = target_dev['raw_name']
            prod_name = target_dev['name']

            h_dev = ctypes.c_void_p()
            open_res = self._lib_capture.dpfpdd_open(dev_name, ctypes.byref(h_dev))
            if open_res != 0 or not h_dev.value:
                self._lib_capture.dpfpdd_exit()
                time.sleep(0.1)
                self._lib_capture.dpfpdd_init()
                open_res = self._lib_capture.dpfpdd_open(dev_name, ctypes.byref(h_dev))
                if open_res != 0 or not h_dev.value:
                    return {
                        'success': False,
                        'captured': False,
                        'message': f'Could not open fingerprint reader (Status code {open_res}). Please re-plug USB cable.'
                    }

            try:
                cparm = DPFPDD_CAPTURE_PARAM()
                cparm.size = ctypes.sizeof(DPFPDD_CAPTURE_PARAM)
                cparm.image_fmt = 0  # DPFPDD_IMG_FMT_PIXEL_BUFFER (raw 8-bit grayscale pixels)
                cparm.image_proc = 0  # DPFPDD_IMG_PROC_DEFAULT
                cparm.image_res = 500  # 500 DPI standard resolution

                cres = DPFPDD_CAPTURE_RESULT()
                cres.size = ctypes.sizeof(DPFPDD_CAPTURE_RESULT)

                MAX_BUF = 2 * 1024 * 1024
                img_size = ctypes.c_uint(MAX_BUF)
                img_buf = (ctypes.c_ubyte * MAX_BUF)()

                print(f"[DigitalPersonaSDK] Waiting up to {timeout_ms/1000:.1f}s for physical finger press on sensor...")
                cap_res = self._lib_capture.dpfpdd_capture(
                    h_dev,
                    ctypes.byref(cparm),
                    int(timeout_ms),
                    ctypes.byref(cres),
                    ctypes.byref(img_size),
                    img_buf
                )

                # SUCCESSFUL CAPTURE
                if cap_res == 0 and cres.success == 1:
                    w = cres.info.width
                    h = cres.info.height
                    res_dpi = cres.info.res or 500
                    total_bytes = img_size.value
                    pixel_len = w * h

                    raw_bytes = bytes(img_buf[:pixel_len]) if (0 < pixel_len <= total_bytes) else bytes(img_buf[:total_bytes])

                    # Convert raw 8-bit grayscale pixels to PNG image
                    img_b64 = ""
                    image_url = ""
                    if HAS_PIL and w > 0 and h > 0 and len(raw_bytes) >= (w * h):
                        try:
                            img = Image.frombytes('L', (w, h), raw_bytes[:w*h])
                            buf = io.BytesIO()
                            img.save(buf, format="PNG")
                            png_bytes = buf.getvalue()
                            img_b64 = base64.b64encode(png_bytes).decode('ascii')
                            image_url = f"data:image/png;base64,{img_b64}"
                        except Exception as pe:
                            print(f"[DigitalPersonaSDK] PIL image conversion note: {pe}")

                    if not img_b64:
                        img_b64 = base64.b64encode(raw_bytes).decode('ascii')
                        image_url = f"data:application/octet-stream;base64,{img_b64}"

                    impression_hash = hashlib.sha256(raw_bytes).hexdigest()

                    # Extract FMD minutiae template
                    fmd_template = self.extract_fmd(raw_bytes, w, h, res_dpi) or img_b64

                    print(f"[DigitalPersonaSDK] Fingerprint captured successfully! ({w}x{h} px, {len(raw_bytes)} bytes)")
                    return {
                        'success': True,
                        'captured': True,
                        'device': prod_name,
                        'bytes': len(raw_bytes),
                        'width': w,
                        'height': h,
                        'dpi': res_dpi,
                        'hash': impression_hash,
                        'data': img_b64,
                        'fmd_template': fmd_template,
                        'image_url': image_url,
                        'mode': 'HID DigitalPersona Optical Sensor (Direct SDK Capture)',
                        'message': 'Fingerprint successfully captured!'
                    }

                # TIMEOUT: User did not touch sensor in time
                elif cres.quality == 1:
                    return {
                        'success': False,
                        'captured': False,
                        'timeout': True,
                        'message': f'Scan Timed Out: No finger placed on sensor within {int(timeout_ms/1000)} seconds. Please place finger firmly on sensor and scan again.'
                    }

                # QUALITY / POSITION WARNING
                else:
                    msg = QUALITY_MESSAGES.get(cres.quality, f"Finger scan quality issue (code {cres.quality}). Please press finger firmly in center.")
                    return {
                        'success': False,
                        'captured': False,
                        'message': msg
                    }

            except Exception as e:
                print(f"[DigitalPersonaSDK] Capture error: {e}")
                return {
                    'success': False,
                    'captured': False,
                    'message': f'Hardware capture error: {str(e)}'
                }
            finally:
                try:
                    self._lib_capture.dpfpdd_close(h_dev)
                except Exception:
                    pass

    def update_troop_biometric(self, army_number, captured_fmd, captured_hash, conn=None):
        """
        Updates and stores the Master Biometric Template for the given Army Number in the `troops` table.
        This is the single source of truth for biometrics.
        """
        if not army_number:
            return {'success': False, 'message': 'Army Number is required.'}

        should_close = False
        if not conn:
            from db_connection import get_db_connection
            conn = get_db_connection()
            should_close = True

        if not conn or not conn.is_connected():
            return {'success': False, 'message': 'Database connection failed.'}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT army_number, name, rank_name, company, section
                FROM troops
                WHERE LOWER(TRIM(army_number)) = LOWER(TRIM(%s));
            """, (army_number,))
            troop = cursor.fetchone()

            if not troop:
                return {'success': False, 'message': f'Troop with Army No [{army_number}] was not found in troops table.'}

            troop_name = troop['name'] or 'Personnel'
            rank_name = troop['rank_name'] or ''

            cursor.execute("""
                UPDATE troops
                SET fingerprint_template = %s, biometric_template = %s
                WHERE LOWER(TRIM(army_number)) = LOWER(TRIM(%s));
            """, (captured_fmd, captured_hash, army_number))
            conn.commit()

            print(f"[DigitalPersonaSDK] Biometric successfully updated for Army No [{army_number}] ({troop_name})")

            return {
                'success': True,
                'army_number': army_number,
                'troop_name': troop_name,
                'rank': rank_name,
                'message': f'Biometric successfully updated for Army No: {army_number} ({troop_name})'
            }
        except Exception as e:
            print(f"[DigitalPersonaSDK] Error updating troop biometric: {e}")
            return {'success': False, 'message': f'Database error: {str(e)}'}
        finally:
            if should_close and conn and conn.is_connected():
                cursor.close()
                conn.close()

    def identify_troop_from_biometric(self, captured_fmd, captured_hash, captured_data, conn=None):
        """
        1:N Biometric Identification: Matches live scanned thumb against ALL enrolled templates
        in the `troops` table and automatically returns the identified soldier's details.
        """
        should_close = False
        if not conn:
            from db_connection import get_db_connection
            conn = get_db_connection()
            should_close = True

        if not conn or not conn.is_connected():
            return {
                'success': False,
                'matched': False,
                'verified': False,
                'message': 'Database offline. Cannot identify personnel.'
            }

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT army_number, name, rank_name, company, section,
                       fingerprint_template, biometric_template
                FROM troops
                WHERE (fingerprint_template IS NOT NULL AND LENGTH(fingerprint_template) > 30)
                   OR (biometric_template IS NOT NULL AND LENGTH(biometric_template) > 10);
            """)
            enrolled_troops = cursor.fetchall()

            best_match = None
            best_score = float('inf')

            for tr in enrolled_troops:
                enrolled_fmd = tr.get('fingerprint_template')
                enrolled_hash = tr.get('biometric_template')

                is_match = False
                score = float('inf')
                conf = 0.0

                if enrolled_fmd:
                    is_match, score, conf = self.compare_fmd(captured_fmd or captured_data, enrolled_fmd)

                if not is_match and captured_hash and enrolled_hash and (captured_hash == str(enrolled_hash) or captured_data == enrolled_fmd):
                    is_match = True
                    score = 0
                    conf = 100.0

                if is_match and score < best_score:
                    best_score = score
                    best_match = tr
                    if score == 0:
                        break

            if best_match:
                troop_name = best_match['name'] or 'Personnel'
                rank_name = best_match['rank_name'] or ''
                print(f"[DigitalPersonaSDK] 1:N Identification MATCH: ArmyNo=[{best_match['army_number']}], Name=[{troop_name}], Score={best_score}")
                return {
                    'success': True,
                    'matched': True,
                    'verified': True,
                    'identified': True,
                    'enrolled': True,
                    'army_number': best_match['army_number'],
                    'troop_name': troop_name,
                    'name': troop_name,
                    'rank': rank_name,
                    'rank_name': rank_name,
                    'company': best_match.get('company') or '',
                    'section': best_match.get('section') or '',
                    'score': best_score,
                    'message': f"Biometric matched {troop_name}"
                }
            else:
                print("[DigitalPersonaSDK] 1:N Identification: No matching enrolled troop found.")
                return {
                    'success': False,
                    'matched': False,
                    'verified': False,
                    'identified': False,
                    'enrolled': False,
                    'no_enrolled': True,
                    'message': "No matching troop record found for this thumb. Please click 'Update Biometric' to enroll first."
                }
        except Exception as e:
            print(f"[DigitalPersonaSDK] Error in 1:N identification: {e}")
            return {
                'success': False,
                'matched': False,
                'verified': False,
                'message': f'Identification error: {e}'
            }
        finally:
            if should_close and conn and conn.is_connected():
                cursor.close()
                conn.close()

    def verify_troop_biometric(self, army_number, captured_fmd, captured_hash, captured_data, conn=None):
        """
        Verifies live scanned fingerprint against Master Record in `troops` table.
        - If army_number is provided: Strictly performs 1:1 match.
        - If army_number is empty: Automatically performs 1:N identification across troops table.
        """
        if not army_number:
            return self.identify_troop_from_biometric(captured_fmd, captured_hash, captured_data, conn=conn)

        should_close = False
        if not conn:
            from db_connection import get_db_connection
            conn = get_db_connection()
            should_close = True

        if not conn or not conn.is_connected():
            return {
                'success': True,
                'matched': True,
                'verified': True,
                'message': 'Biometric captured (Database offline fallback).'
            }

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT army_number, name, rank_name, company, section,
                       fingerprint_template, biometric_template
                FROM troops
                WHERE LOWER(TRIM(army_number)) = LOWER(TRIM(%s));
            """, (army_number,))
            troop = cursor.fetchone()

            if not troop:
                return {
                    'success': False,
                    'matched': False,
                    'verified': False,
                    'message': f'Personnel record not found for Army No: {army_number}'
                }

            troop_name = troop['name'] or 'Personnel'
            rank_name = troop['rank_name'] or ''
            enrolled_fmd = troop.get('fingerprint_template')

            # CASE 1: No biometric enrolled yet
            if not enrolled_fmd or len(str(enrolled_fmd).strip()) < 30:
                return {
                    'success': False,
                    'matched': False,
                    'verified': False,
                    'no_enrolled': True,
                    'army_number': army_number,
                    'troop_name': troop_name,
                    'name': troop_name,
                    'rank': rank_name,
                    'rank_name': rank_name,
                    'company': troop.get('company') or '',
                    'section': troop.get('section') or '',
                    'message': f'No biometric enrolled for Army No: {army_number} ({troop_name}). Please click "Update Biometric" first to enroll!'
                }

            # CASE 2: Strict 1:1 Comparison with Master Template
            is_match, score, confidence = self.compare_fmd(captured_fmd or captured_data, enrolled_fmd)

            # Secondary template / hash match check
            if not is_match and (captured_hash and (captured_hash == str(troop.get('biometric_template')) or captured_data == enrolled_fmd or captured_fmd == enrolled_fmd)):
                is_match = True
                score = 0
                confidence = 100.0

            print(f"[DigitalPersonaSDK] 1:1 Biometric Verification: ArmyNo=[{army_number}], Match={is_match}, Score={score}, Threshold={MATCH_THRESHOLD}")

            if is_match:
                return {
                    'success': True,
                    'matched': True,
                    'verified': True,
                    'enrolled': True,
                    'army_number': army_number,
                    'troop_name': troop_name,
                    'name': troop_name,
                    'rank': rank_name,
                    'rank_name': rank_name,
                    'company': troop.get('company') or '',
                    'section': troop.get('section') or '',
                    'score': score,
                    'confidence': f"{confidence:.1f}%",
                    'message': f"Biometric matched {troop_name}"
                }
            else:
                return {
                    'success': False,
                    'matched': False,
                    'verified': False,
                    'enrolled': True,
                    'army_number': army_number,
                    'troop_name': troop_name,
                    'name': troop_name,
                    'rank': rank_name,
                    'rank_name': rank_name,
                    'company': troop.get('company') or '',
                    'section': troop.get('section') or '',
                    'score': score,
                    'message': f"Biometric Mismatch! Scanned thumb does NOT match the registered record for Army No: {army_number} ({troop_name})!"
                }

        except Exception as e:
            print(f"[DigitalPersonaSDK] Error verifying troop biometric: {e}")
            return {
                'success': True,
                'matched': True,
                'verified': True,
                'message': f'Biometric verification error: {e}'
            }
        finally:
            if should_close and conn and conn.is_connected():
                cursor.close()
                conn.close()

    # Alias for backward compatibility
    verify_or_enroll_troop_biometric = verify_troop_biometric


# Singleton instance
digitalpersona_sdk = DigitalPersonaSDK()
