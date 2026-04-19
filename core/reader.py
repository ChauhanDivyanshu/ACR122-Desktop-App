# # # from smartcard.System import readers

# # # class NFCReader:
# # #     def __init__(self):
# # #         self.reader = None
# # #         self.connection = None

# # #     def connect_reader(self):
# # #         r = readers()
# # #         if not r:
# # #             raise Exception("No NFC Reader Found")
# # #         self.reader = r[0]
# # #         print("Reader Connected:", self.reader)

# # #     def connect_card(self):
# # #         try:
# # #             self.connection = self.reader.createConnection()
# # #             self.connection.connect()
# # #             return True
# # #         except:
# # #             return False
        
# # #     def send_apdu(self, cmd):
# # #         apdu = [int(x, 16) for x in cmd.split()]
# # #         response, sw1, sw2 = self.connection.transmit(apdu)
# # #         return response, sw1, sw2
    
# # #     def get_uid(self):
# # #         if not self.connect_card():
# # #             return None
        
# # #         cmd = "FF CA 00 00 00"
# # #         response, sw1, sw2 = self.send_apdu(cmd)
# # #         if sw1 == 0x90:
# # #             uid = ''.join(format(x, '02X') for x in response)
# # #             return uid
        
# # #         return None


# from smartcard.System import readers
# from smartcard.Exceptions import CardConnectionException, NoCardException
# from loguru import logger

# class NFCReader:
#     def __init__(self):
#         self.reader = None
#         self.connection = None

#     def connect_reader(self):
#         r = readers()
#         if not r:
#             raise Exception("No NFC reader found")
#         self.reader = r[0]
#         logger.info(f"Reader connected: {self.reader}")

#     def connect_card(self):
#         try:
#             self.connection = self.reader.createConnection()
#             self.connection.connect()
#             return True
#         except NoCardException:
#             return False  # Card nahi hai — normal case
#         except CardConnectionException as e:
#             logger.warning(f"Card connection failed: {e}")
#             return False
#         # bare except NAHI — otherwise KeyboardInterrupt bhi catch ho jaata

#     def send_apdu(self, cmd):
#         apdu = [int(x, 16) for x in cmd.split()]
#         response, sw1, sw2 = self.connection.transmit(apdu)
#         if sw1 not in (0x90, 0x61):  # 0x61 = more data available
#             logger.warning(f"APDU warning: SW={sw1:02X}{sw2:02X} cmd={cmd}")
#         return response, sw1, sw2

#     def get_uid(self):
#         if not self.connect_card():
#             return None
#         try:
#             cmd = "FF CA 00 00 00"
#             response, sw1, sw2 = self.send_apdu(cmd)
#             if sw1 == 0x90:
#                 uid = ''.join(format(x, '02X') for x in response)
#                 return uid
#             return None
#         except Exception as e:
#             logger.error(f"get_uid failed: {e}")
#             return None

# from smartcard.System import readers


# class NFCReader:
#     def __init__(self):
#         self.connection = None

#     def connect(self):
#         r = readers()

#         if not r:
#             raise Exception(" No NFC Reader Found")

#         print("Available Readers:", r)

#         self.connection = r[0].createConnection()

#         print(" Tap card to connect...")

#         while True:
#             try:
#                 self.connection.connect()
#                 print(" Reader Connected:", r[0])
#                 break
#             except:
#                 pass

#     def send_apdu(self, cmd):
#         apdu = [int(x, 16) for x in cmd.split()]
#         response, sw1, sw2 = self.connection.transmit(apdu)
#         return response, sw1, sw2

#     def get_uid(self):
#         try:
#             cmd = "FF CA 00 00 00"
#             response, sw1, sw2 = self.send_apdu(cmd)

#             if sw1 == 0x90:
#                 uid = ''.join(format(x, '02X') for x in response)
#                 return uid

#         except:
#             return None



# from smartcard.System import readers
# from smartcard.Exceptions import (
#     CardConnectionException,
#     NoCardException
# )
# from loguru import logger


# class NFCReader:
#     def __init__(self):
#         self.reader = None
#         self.connection = None

#     # ─────────────────────────────────────────
#     # READER CONNECTION
#     # ─────────────────────────────────────────

#     def find_reader(self) -> bool:
#         available = readers()
#         print(f"Available Readers: {available}")
#         for r in available:
#             if "ACR122" in str(r) or "ACS" in str(r):
#                 self.reader = r
#                 return True
#         return False

#     def connect_reader(self):
#         if not self.find_reader():
#             raise Exception("ACR122U not found")
#         print(f" Reader Connected: {self.reader}")

#     def connect_card(self) -> bool:
#         """Card se connection banao"""
#         try:
#             self.connection = self.reader.createConnection()
#             self.connection.connect()
#             return True

#         except NoCardException:
#             return False

#         except CardConnectionException as e:
#             error_str = str(e)
#             if "0x80100069" in error_str or "removed" in error_str.lower():
#                 logger.warning("Card removed during connect")
#             else:
#                 logger.warning(f"Connection error: {e}")
#             return False

#         except Exception as e:
#             error_str = str(e)
#             if "0x80100069" in error_str or "0x80100068" in error_str:
#                 return False
#             logger.error(f"Unexpected connect error: {e}")
#             return False

#     def disconnect_card(self):
#         """Safe disconnect"""
#         try:
#             if self.connection:
#                 self.connection.disconnect()
#         except Exception:
#             pass
#         finally:
#             self.connection = None

#     # ─────────────────────────────────────────
#     # UID
#     # ─────────────────────────────────────────

#     def get_uid(self) -> str | None:
#         """Card UID read karo"""
#         if not self.connect_card():
#             return None
#         try:
#             # Standard GET UID APDU
#             apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
#             response, sw1, sw2 = self.connection.transmit(apdu)

#             if sw1 == 0x90:
#                 uid = "".join(f"{b:02X}" for b in response)
#                 return uid
#             return None

#         except Exception as e:
#             self._handle_card_error(e, "get_uid")
#             return None

#     # ─────────────────────────────────────────
#     # READ PAGE — CORRECT APDU
#     # ─────────────────────────────────────────

#     def read_page(self, page: int) -> list | None:
#         """
#         NTAG213 page read karo.

#         Correct APDU:
#         FF B0 00 [PAGE] 04
#         CLA=FF, INS=B0 (READ BINARY), P1=00, P2=page, Le=04
#         """
#         try:
#             apdu = [
#                 0xFF,   # CLA
#                 0xB0,   # INS - READ BINARY
#                 0x00,   # P1
#                 page,   # P2 - page number
#                 0x04    # Le - 4 bytes read
#             ]

#             logger.debug(f"READ page {page}: {[hex(x) for x in apdu]}")
#             response, sw1, sw2 = self.connection.transmit(apdu)
#             logger.debug(
#                 f"READ response: SW={sw1:02X}{sw2:02X} "
#                 f"Data={bytes(response).hex().upper()}"
#             )

#             if sw1 == 0x90:
#                 return list(response[:4])

#             logger.warning(
#                 f"Read page {page} failed: SW={sw1:02X}{sw2:02X}"
#             )
#             return None

#         except Exception as e:
#             self._handle_card_error(e, f"read_page {page}")
#             return None

#     # ─────────────────────────────────────────
#     # WRITE PAGE — CORRECT APDU
#     # ─────────────────────────────────────────

#     def write_page(self, page: int, data: list) -> bool:
#         """
#         NTAG213 page write karo — 4 bytes.

#         Correct APDU:
#         FF D6 00 [PAGE] 04 [D0 D1 D2 D3]
#         CLA=FF, INS=D6 (UPDATE BINARY), P1=00, P2=page, Lc=04, Data
#         """
#         if len(data) != 4:
#             raise ValueError(f"Page data must be 4 bytes, got {len(data)}")

#         try:
#             apdu = [
#                 0xFF,   # CLA
#                 0xD6,   # INS - UPDATE BINARY
#                 0x00,   # P1
#                 page,   # P2 - page number
#                 0x04,   # Lc - 4 bytes data
#             ] + list(data)  # Data bytes

#             logger.debug(
#                 f"WRITE page {page}: "
#                 f"data={[hex(x) for x in data]}"
#             )
#             response, sw1, sw2 = self.connection.transmit(apdu)
#             logger.debug(
#                 f"WRITE response: SW={sw1:02X}{sw2:02X}"
#             )

#             if sw1 == 0x90:
#                 return True

#             logger.warning(
#                 f"Write page {page} failed: SW={sw1:02X}{sw2:02X}"
#             )
#             return False

#         except Exception as e:
#             self._handle_card_error(e, f"write_page {page}")
#             return False

#     # ─────────────────────────────────────────
#     # CARD TYPE DETECTION
#     # ─────────────────────────────────────────

#     def detect_card_type(self) -> str:
#         """Card type detect karo"""
#         try:
#             return self._get_ntag_version()
#         except Exception as e:
#             logger.error(f"Card type detection failed: {e}")
#             return "UNKNOWN"

#     def _get_ntag_version(self) -> str:
#         """
#         NTAG GET_VERSION command.

#         Pseudo-APDU for ACR122U:
#         FF 00 00 00 01 60
#         """
#         try:
#             apdu = [0xFF, 0x00, 0x00, 0x00, 0x01, 0x60]
#             response, sw1, sw2 = self.connection.transmit(apdu)

#             if sw1 == 0x90 and len(response) >= 8:
#                 size = response[6]
#                 mapping = {
#                     0x0F: "NTAG213",
#                     0x11: "NTAG215",
#                     0x13: "NTAG216",
#                 }
#                 card_type = mapping.get(size, "NTAG_UNKNOWN")
#                 logger.debug(f"Card type: {card_type}")
#                 return card_type

#             return "NTAG_UNKNOWN"

#         except Exception as e:
#             logger.error(f"GET_VERSION failed: {e}")
#             return "NTAG_UNKNOWN"

#     # ─────────────────────────────────────────
#     # CARD PRESENT CHECK
#     # ─────────────────────────────────────────

#     def _is_card_present(self) -> bool:
#         """Card abhi bhi reader pe hai?"""
#         try:
#             apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
#             response, sw1, sw2 = self.connection.transmit(apdu)
#             return sw1 == 0x90
#         except Exception:
#             return False

#     # ─────────────────────────────────────────
#     # ERROR HANDLER
#     # ─────────────────────────────────────────

#     def _handle_card_error(self, error: Exception, context: str):
#         """Errors classify karke log karo"""
#         error_str = str(error).lower()

#         removed_signals = [
#             "0x80100069",
#             "0x80100068",
#             "removed",
#             "not present",
#             "no smartcard",
#         ]

#         is_removed = any(s in error_str for s in removed_signals)

#         if is_removed:
#             logger.warning(f"[{context}] Card removed")
#         else:
#             logger.error(f"[{context}] Error: {error}")


from smartcard.System import readers
from smartcard.Exceptions import CardConnectionException, NoCardException
from smartcard.util import toHexString
from loguru import logger


# ATR signatures — yeh bytes card ke manufacturer se fix hain
ATR_MAP = {
    # NTAG213 — most common NFC sticker
    "3B8F8001804F0CA000000306030001000000006A": "NTAG213",
    # NTAG215
    "3B8F8001804F0CA000000306030300000000006C": "NTAG215",
    # NTAG216
    "3B8F8001804F0CA000000306030400000000006B": "NTAG216",
    # MIFARE Classic 1K
    "3B8F8001804F0CA0000003060300010000000068": "MIFARE_1K",
    # MIFARE Classic 4K
    "3B8F8001804F0CA0000003060300020000000069": "MIFARE_4K",
    # MIFARE Ultralight (NTAG ke jaisa lightweight)
    "3B8F8001804F0CA000000306030200000000006B": "MIFARE_UL",
}

# ATR mein partial match — last few bytes vary karte hain kabhi kabhi
ATR_PARTIAL_MAP = {
    "3B8F8001804F0CA00000030603": {
        "01": "NTAG213",
        "03": "NTAG215",
        "04": "NTAG216",
        "02": "MIFARE_UL",
    }
}


class NFCReader:
    def __init__(self):
        self.reader = None
        self.connection = None
        self._current_card_type = None

    def connect_reader(self):
        r = readers()
        if not r:
            raise Exception("No NFC reader found. Check USB connection.")
        # ACR122U prefer karo agar multiple readers hain
        for rdr in r:
            if "ACR122" in str(rdr) or "ACS" in str(rdr):
                self.reader = rdr
                logger.info(f"ACR122U found: {rdr}")
                return
        # Fallback — pehla reader lo
        self.reader = r[0]
        logger.info(f"Reader connected (non-ACR122U): {r[0]}")

    def connect_card(self):
        """Card present hai? Connect karo."""
        try:
            self.connection = self.reader.createConnection()
            self.connection.connect()
            return True
        except NoCardException:
            return False
        except CardConnectionException:
            return False
        except Exception as e:
            logger.debug(f"connect_card: {e}")
            return False

    def disconnect_card(self):
        try:
            if self.connection:
                self.connection.disconnect()
        except Exception:
            pass
        self.connection = None
        self._current_card_type = None

    def send_apdu(self, cmd_hex: str):
        """
        cmd_hex: space-separated hex string — "FF CA 00 00 00"
        returns: (response_bytes, sw1, sw2)
        """
        apdu = [int(x, 16) for x in cmd_hex.strip().split()]
        try:
            response, sw1, sw2 = self.connection.transmit(apdu)
            logger.debug(f"APDU {cmd_hex} → SW={sw1:02X}{sw2:02X} data={toHexString(response)}")
            return response, sw1, sw2
        except Exception as e:
            logger.error(f"APDU transmit failed: {e}")
            raise

    # ─────────────────────────────────────────
    # CARD TYPE DETECTION — MAIN FIX
    # ─────────────────────────────────────────

    def get_atr(self):
        """ATR bytes read karo — card ka 'identity card'"""
        try:
            # Method 1: pyscard ka built-in ATR
            atr = self.connection.getATR()
            if atr:
                atr_hex = ''.join(format(b, '02X') for b in atr)
                logger.info(f"ATR: {atr_hex}")
                return atr_hex
        except Exception:
            pass

        # Method 2: ACR122U ka specific ATR command
        try:
            response, sw1, sw2 = self.send_apdu("FF CA 01 00 00")
            if sw1 == 0x90:
                atr_hex = ''.join(format(b, '02X') for b in response)
                logger.info(f"ATR (via cmd): {atr_hex}")
                return atr_hex
        except Exception:
            pass

        return None

    def detect_card_type(self):
        """
        ATR se card type detect karo.
        Returns: "NTAG213" / "NTAG216" / "MIFARE_1K" / "UNKNOWN"
        """
        atr = self.get_atr()
        if not atr:
            logger.warning("Could not read ATR")
            return "UNKNOWN"

        # Exact match try karo
        if atr in ATR_MAP:
            card_type = ATR_MAP[atr]
            logger.info(f"Card detected (exact): {card_type}")
            self._current_card_type = card_type
            return card_type

        # Partial match — ATR ka prefix check karo
        for prefix, type_map in ATR_PARTIAL_MAP.items():
            if atr.startswith(prefix):
                # Byte 13-14 (index 26-27) card subtype batata hai
                subtype_byte = atr[26:28] if len(atr) > 27 else ""
                if subtype_byte in type_map:
                    card_type = type_map[subtype_byte]
                    logger.info(f"Card detected (partial): {card_type}")
                    self._current_card_type = card_type
                    return card_type

        # GET VERSION command try karo (NTAG specific)
        card_type = self._detect_via_get_version()
        if card_type:
            self._current_card_type = card_type
            return card_type

        logger.warning(f"Unknown card ATR: {atr}")
        self._current_card_type = "UNKNOWN"
        return "UNKNOWN"

    def _detect_via_get_version(self):
        """
        NTAG GET VERSION command — ATR se pata nahi chala toh yeh try karo.
        Response byte 6 = storage size:
          0x0F = NTAG213 (144 bytes)
          0x11 = NTAG215 (504 bytes)  
          0x13 = NTAG216 (888 bytes)
        """
        try:
            # GET VERSION: FF 00 00 00 01 60 wrapped in ACR122U pseudo-APDU
            response, sw1, sw2 = self.send_apdu("FF 00 00 00 01 60")
            if sw1 == 0x90 and len(response) >= 7:
                size_byte = response[6]
                version_map = {0x0F: "NTAG213", 0x11: "NTAG215", 0x13: "NTAG216"}
                if size_byte in version_map:
                    card_type = version_map[size_byte]
                    logger.info(f"Card detected (GET VERSION): {card_type}")
                    return card_type
        except Exception as e:
            logger.debug(f"GET VERSION failed (not NTAG?): {e}")
        return None

    def get_uid(self):
        """Card ka unique ID read karo."""
        if not self.connect_card():
            return None
        try:
            response, sw1, sw2 = self.send_apdu("FF CA 00 00 00")
            if sw1 == 0x90:
                uid = ''.join(format(x, '02X') for x in response)
                logger.debug(f"UID: {uid}")
                return uid
            return None
        except Exception as e:
            logger.error(f"get_uid error: {e}")
            return None

    def read_page(self, page_num: int):
        """NTAG page read (4 bytes per page)."""
        cmd = f"FF 00 00 00 05 30 {page_num:02X} 00 00 10"
        # Simpler: direct READ command
        cmd = f"FF B0 00 {page_num:02X} 04"
        response, sw1, sw2 = self.send_apdu(cmd)
        if sw1 == 0x90:
            return response
        return None

    def write_page(self, page_num: int, data_4bytes: list):
        """
        NTAG page write (exactly 4 bytes).
        WRITE command: A2 <page> <4 bytes>
        ACR122U wrapper: FF 00 00 00 07 A2 <page> <b0> <b1> <b2> <b3>
        """
        assert len(data_4bytes) == 4, "NTAG write needs exactly 4 bytes"
        d = data_4bytes
        cmd = f"FF 00 00 00 07 A2 {page_num:02X} {d[0]:02X} {d[1]:02X} {d[2]:02X} {d[3]:02X}"
        response, sw1, sw2 = self.send_apdu(cmd)
        if sw1 != 0x90:
            raise Exception(f"Write page {page_num} failed: SW={sw1:02X}{sw2:02X}")
        return True

    def get_card_info(self):
        """
        Ek saath sab info return karo — UI display ke liye.
        Phone pe tap karoge toh yahi data dikhega (from NDEF).
        """
        if not self.connect_card():
            return None
        uid = self.get_uid()
        card_type = self.detect_card_type()
        return {
            "uid": uid,
            "type": card_type,
            "connected": True
        } 