# import sys
# import time
# from loguru import logger
# from smartcard.System import readers as get_readers
# from core.writer import NFCWriter, NDEFBuilder

# #NFC READER

# class NFCReader:
#     """
#     Hardware Layer - Talks directly to the ACR122U.
#     Only USB/APDU communication is here.
#     No NDEF/write logic here.
#     """

#     def __init__(self):
#         self.reader     = None
#         self.connection = None

#     def connect_reader(self):
#         """
#         Find and connect to AIR122.
#         Prefer AIX/AIR122 among multiple readers.
#         """
#         available = get_readers()
#         print(f"  Available readers: {available}")

#         if not available:
#             raise Exception("No reader found! Please plug in USB and try again.")

#         for r in available:
#             name = str(r).upper()
#             if "ACR122" in name or "ACS" in name:
#                 self.reader = r
#                 print(f"  Reader connected: {r}")
#                 return

#         # Fallback — first reader
#         self.reader = available[0]
#         logger.warning(f"ACR122U not found, fallback: {self.reader}")

#     def connect_card(self) -> bool:
#         """
#         Create a fresh connection with the card.
#         A new connection every time it's reliable.
#         """
#         try:
#             self.connection = self.reader.createConnection()
#             self.connection.connect()
#             return True
#         except Exception as e:
#             err = str(e).lower()
#             expected = [
#                 "no card", "removed", "0x80100069",
#                 "no smartcard", "card not present", "sharing violation"
#             ]
#             if any(x in err for x in expected):
#                 return False
#             logger.warning(f"connect_card unexpected: {e}")
#             return False

#     def disconnect_card(self):
#         """Safe disconnect."""
#         try:
#             if self.connection:
#                 self.connection.disconnect()
#         except Exception:
#             pass
#         finally:
#             self.connection = None

#     def _transmit(self, apdu: list):

#         """
#         Send to the ADD/ODM card.
#         If there is no connection, try reconnecting.
#         Returns: (response, sv1, sv2) tuple or non-failure.
#         """

#         try:
#             #No connection → connect with
#             if not self.connection:
#                 if not self.connect_card():
#                     return None

#             response, sw1, sw2 = self.connection.transmit(apdu)
#             return response, sw1, sw2

#         except Exception as e:
#             logger.debug(f"_transmit error, reconnecting: {e}")
#             try:
#                 self.connect_card()
#                 response, sw1, sw2 = self.connection.transmit(apdu)
#                 return response, sw1, sw2
#             except Exception as e2:
#                 logger.warning(f"_transmit retry failed: {e2}")
#                 return None

#     def get_uid(self) -> str | None:
#         """
#         Detect Card UID.
#         APDU: FF CA 00 00 00
#         """
#         if not self.connect_card():
#             return None
#         try:
#             result = self._transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
#             if result and result[1] == 0x90:
#                 return "".join(f"{b:02X}" for b in result[0])
#             return None
#         except Exception:
#             return None

#     def is_card_present(self) -> bool:
#         """
#         Quick check if the card is tap on the reader.
#         Calling in between.
#         """
#         try:
#             result = self._transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
#             return result is not None and result[1] == 0x90
#         except Exception:
#             return False


# # ═══════════════════════════════════════════════════════════
# #  Display helpers
# # ═══════════════════════════════════════════════════════════

# def print_header(title: str):
#     width = 54
#     print("\n" + "═" * width)
#     print(f"  {title}")
#     print("═" * width)


# def print_section(title: str):
#     print(f"\n{'─' * 46}")
#     print(f"  {title}")
#     print("─" * 46)


# def print_ndef_preview(payload: bytes, data_type: str, data: str):
#     print_section("NDEF Preview")
#     print(f"  Type      : {data_type.upper()}")
#     print(f"  Content   : {data[:60]}{'...' if len(data) > 60 else ''}")
#     print(f"  Bytes     : {len(payload)}")
#     print(f"  Hex       : {payload.hex().upper()[:64]}"
#           f"{'...' if len(payload) > 32 else ''}")

#     pages = [payload[i:i+4].hex().upper() for i in range(0, len(payload), 4)]
#     print(f"  Pages({len(pages)})  : {' | '.join(pages[:6])}"
#           f"{'...' if len(pages) > 6 else ''}")


# # ═══════════════════════════════════════════════════════════
# #  Card wait loop
# # ═══════════════════════════════════════════════════════════

# def wait_for_card(reader: NFCReader, timeout: int = 60) -> str | None:
#     """
#     Wait for the card to be tapped.
#     Returns UID string or None on timeout.
#     """
#     print("\n  Card tap on the Reader...")
#     print(f"  Timeout: {timeout} seconds")

#     start = time.time()
#     dots  = 0

#     while True:
#         elapsed = time.time() - start
#         if elapsed > timeout:
#             print("\n\n  Timeout! No cards detected.")
#             return None

#         uid = reader.get_uid()
#         if uid:
#             print(f"\n\n  Card detected!")
#             return uid

#         dots = (dots + 1) % 4
#         remaining = int(timeout - elapsed)
#         print(
#             f"\r  {'.' * dots}{' ' * (3 - dots)}  ({remaining}s)",
#             end="", flush=True
#         )
#         time.sleep(0.2)


# # ═══════════════════════════════════════════════════════════
# #  User input
# # ═══════════════════════════════════════════════════════════

# def get_user_choice(prompt: str, valid: list) -> str:
#     while True:
#         ans = input(prompt).strip()
#         if ans in valid:
#             return ans
#         print(f"  Invalid. Choose from: {valid}")


# def get_data_from_user() -> tuple | None:
#     """
#     Take data type and content from the user.
#     Returns: (data_type, content) or None if cancelled.
#     DATA TYPES:
#       url → browser will open on phone tap
#       text → text will appear on phone tap
#       raw → hex bytes direct write
#     """
#     print_section("Please Choose the Type")
#     print("  1. URL  — website link (Open Browser)")
#     print("  2. TEXT — plain text   (Show text)")
#     #print("  3. RAW  — hex bytes    (advanced)")
#     print("  0. Cancel")

#     choice = get_user_choice("\n  Choice (0-3): ", ["0", "1", "2", "3"])

#     if choice == "0":
#         return None

#     # ── URL ──────────────────────────────────────────────
#     if choice == "1":
#         print("\n  Examples: https://google.com | http://192.168.1.1 | tel:9876543210")
#         while True:
#             url = input("\n  URL: ").strip()
#             if not url:
#                 print("  The URL cannot be empty!")
#                 continue
#             # Auto https add
#             if not any(url.lower().startswith(p) for p in [
#                 "http://", "https://", "ftp://", "tel:", "mailto:"
#             ]):
#                 ans = input(
#                     f"  'https://' add karein? [{url}] → [https://{url}] (y/n): "
#                 ).strip().lower()
#                 if ans == "y":
#                     url = "https://" + url
#             return "url", url

#     # ── TEXT ─────────────────────────────────────────────
#     elif choice == "2":
#         print("\n  Foe Examples Type: Hello | Name: Divyanshu")
#         while True:
#             text = input("\n  Text: ").strip()
#             if not text:
#                 print("  The Text can not be empty!")
#                 continue
#             return "text", text

#     # ── RAW ──────────────────────────────────────────────
#     # elif choice == "3":
#     #     print("\n  Hex bytes (space separated):")
#     #     print("    Example: 03 0A D1 01 06 55 04 67 6F 6F 67 FE")
#     #     while True:
#     #         raw = input("\n  Hex: ").strip()
#     #         if not raw:
#     #             continue
#     #         try:
#     #             bytes.fromhex(raw.replace(" ", "").replace(":", ""))
#     #             return "raw", raw
#     #         except ValueError:
#     #             print("  Invalid hex!")

#     return None


# def ask_clear_first() -> bool:
#     """
#     Whether to clear or not—ask the user explicitly.
#     WHY EXPLICIT?
#     clear() and write() are different—clear is destructive.
#     Clearing on a blank card is a waste of time.
#     Let the user decide.
#     """
#     print_section("Need to clear your card?")
#     print("  Y = Yes, clear it first (old data will be deleted)")
#     print("  N = No, write it straight (if you have a blank card then use it).")

#     ans = get_user_choice("\n  Clear? (y/n): ", ["y", "n", "Y", "N"])
#     return ans.lower() == "y"


# # ═══════════════════════════════════════════════════════════
# #  MAIN
# # ═══════════════════════════════════════════════════════════

# def main():
#     print_header("ACR122U NFC Writer")

#     # ── Step 1: Reader connect ────────────────────────────
#     print_section("Reader Connection")
#     reader = NFCReader()
#     try:
#         reader.connect_reader()
#     except Exception as e:
#         print(f"\n  ERROR: {e}")
#         sys.exit(1)

#     # ── Step 2: Card wait ─────────────────────────────────
#     uid = wait_for_card(reader, timeout=60)
#     if uid is None:
#         print("  Exit.")
#         sys.exit(0)

#     print(f"\n  UID: {uid}")

#     # ── Step 3: Chip detect ───────────────────────────────
#     print_section("Chip Detection")
#     writer   = NFCWriter(reader)
#     chip_info = writer.detect_chip()
#     print()
#     print(writer.get_chip_report())

#     # ── Step 4: ATC counter ───────────────────────────────
#     # Sirf NTAG215 / NTAG216 pe show karo
#     if chip_info.get("atc_supported"):
#         print_section("ATC Counter")
#         atc = writer.read_atc()
#         if atc:
#             print(f"  This tag was scanned : {atc['count']} baar")
#             print(f"  Counter hex              : 0x{atc['count_hex']}")
#             print(f"  Counter raw bytes        : {atc['raw']}")
#         else:
#             print("  ATC is not read.")
#     else:
#         chip_type = chip_info.get("type", "UNKNOWN")
#         if chip_type == "NTAG213":
#             print(f"\n  ATC: There is no counter in NTG213.")
#         elif chip_type == "MIFARE_1K":
#             print(f"\n  ATC: Mifare Classic does not have the concept of Nfc counter.")

#     # ── Step 5: Writable check ────────────────────────────
#     if not chip_info.get("writable", True):
#         print("\n  Card is locked – cannot be entered!")
#         print("  Use another card.")
#         reader.disconnect_card()
#         sys.exit(1)

#     if chip_info.get("type") == "MIFARE_1K":
#         print("\n  NOTE: MIFARE Classic 1K detected.")
#         print("  NDef Write is optimized for the final in this version.")
#         print("  Basic write on MIFARE")

#     if chip_info.get("type") == "UNKNOWN":
#         print("\n  WARNING: Chip type is not detect.")
#         ans = get_user_choice("  Continue anyway? (y/n): ", ["y", "n", "Y", "N"])
#         if ans.lower() == "n":
#             sys.exit(0)

#     # ── Step 6: Data input ────────────────────────────────
#     result = get_data_from_user()
#     if result is None:
#         print("\n  Cancelled.")
#         reader.disconnect_card()
#         sys.exit(0)

#     data_type, data_content = result

#     # ── Step 7: NDEF preview ──────────────────────────────
#     try:
#         preview_bytes = NDEFBuilder().build(data_content, data_type)
#         print_ndef_preview(preview_bytes, data_type, data_content)

#         max_bytes = chip_info.get("user_pages", 35) * 4
#         if len(preview_bytes) > max_bytes:
#             print(f"\n  ERROR: The data is large!")
#             print(f"    Payload : {len(preview_bytes)} bytes")
#             print(f"    Card max: {max_bytes} bytes")
#             sys.exit(1)

#         print(f"\n  Size OK: {len(preview_bytes)} / {max_bytes} bytes")

#     except Exception as e:
#         print(f"\n  Preview error: {e}")
#         sys.exit(1)

#     # ── Step 8: Clear decision ────────────────────────────
#     do_clear = ask_clear_first()

#     # ── Step 9: Final confirm ─────────────────────────────
#     print_section("Write Confirm")
#     print(f"  UID        : {uid}")
#     print(f"  Chip       : {chip_info.get('type', 'UNKNOWN')}")
#     print(f"  Data type  : {data_type.upper()}")
#     print(f"  Content    : {data_content[:60]}")
#     print(f"  Bytes      : {len(preview_bytes)}")
#     print(f"  Clear first: {'YES' if do_clear else 'NO'}")
#     print()
#     print("  Place the card flat on the reader!")
#     print("  Don't remove the cards during the write!")

#     input("\n  To start press Enter..")

#     # ── Step 10: Fresh reconnect ──────────────────────────
#     # User input ke baad connection stale ho sakti hai
#     print("\n  Reconnecting...")
#     reader.disconnect_card()
#     time.sleep(0.3)

#     if not reader.connect_card():
#         print("  Card not received! Card Place on reader.")
#         sys.exit(1)
#     print("  Connection OK")

#     # ── Step 11: Clear (agar user ne choose kiya) ─────────
#     # Clear aur write ALAG calls hain — writer.write_url() clear() call NAHI karta
#     if do_clear:
#         print_section("Clearing Card")
#         cleared = writer.clear()
#         if not cleared:
#             print("  Clear failed — Try to write without clear..")
#         time.sleep(0.2)

#     # ── Step 12: WRITE ────────────────────────────────────
#     print_section("Writing to Card")

#     try:
#         if data_type == "url":
#             success = writer.write_url(data_content, do_verify=True)
#         elif data_type == "text":
#             success = writer.write_text(data_content, do_verify=True)
#         elif data_type == "raw":
#             success = writer.write_raw(data_content, do_verify=True)
#         else:
#             print(f"  Unknown type: {data_type}")
#             success = False

#     except KeyboardInterrupt:
#         print("\n\n  Write interrupted!")
#         success = False
#     except Exception as e:
#         print(f"\n  Unexpected error: {e}")
#         logger.exception("Write error")
#         success = False

#     # ── Step 13: Result ───────────────────────────────────
#     print()
#     if success:
#         print("═" * 54)
#         print("   WRITE SUCCESSFUL!")
#         print("═" * 54)
#         print(f"  UID     : {uid}")
#         print(f"  Chip    : {chip_info.get('type', 'UNKNOWN')}")
#         print(f"  Type    : {data_type.upper()}")
#         print(f"  Content : {data_content[:50]}")
#         print(f"  Bytes   : {len(preview_bytes)}")
#         print()
#         if data_type == "url":
#             print("  Tap on Phone- open in browwer")
#         elif data_type == "text":
#             print("  Tap on Phone → text will appears!")
#         else:
#             print("  Tap on phone → It will appear in the Nfc app!")
#         print("═" * 54)
#     else:
#         print("═" * 54)
#         print("   WRITE FAILED")
#         print("═" * 54)
#         print("  Possible reasons:")
#         print("    The card was removed from the reader")
#         print("    card is locked")
#         print("    Wrong card type")
#         print("    Hardware issue")
#         print("  → Try again")
#         print("═" * 54)

#     reader.disconnect_card()
#     print("\n  Remove the card from the reade.\n")
#     return 0 if success else 1
    
# if __name__ == "__main__":
#     sys.exit(main())

# main.py

import sys
import time
from loguru import logger
from smartcard.System import readers as get_readers
from core.writer import NFCWriter, NDEFBuilder


class NFCReader:
    def __init__(self):
        self.reader     = None
        self.connection = None

    def connect_reader(self):
        available = get_readers()
        print(f"  Available readers: {available}")
        if not available:
            raise Exception(
                "No reader found! Please plug in USB."
            )
        for r in available:
            name = str(r).upper()
            if "ACR122" in name or "ACS" in name:
                self.reader = r
                print(f"  Reader: {r}")
                return
        self.reader = available[0]
        logger.warning(f"Fallback reader: {self.reader}")

    def connect_card(self) -> bool:
        try:
            self.connection = self.reader.createConnection()
            self.connection.connect()
            return True
        except Exception as e:
            err      = str(e).lower()
            expected = [
                "no card", "removed", "0x80100069",
                "no smartcard", "card not present",
                "sharing violation",
            ]
            if any(x in err for x in expected):
                return False
            logger.warning(f"connect_card: {e}")
            return False

    def disconnect_card(self):
        try:
            if self.connection:
                self.connection.disconnect()
        except Exception:
            pass
        finally:
            self.connection = None

    def _transmit(self, apdu: list):
        try:
            if not self.connection:
                if not self.connect_card():
                    return None
            response, sw1, sw2 = self.connection.transmit(apdu)
            return response, sw1, sw2
        except Exception as e:
            logger.debug(f"_transmit retry: {e}")
            try:
                self.connect_card()
                response, sw1, sw2 = self.connection.transmit(apdu)
                return response, sw1, sw2
            except Exception as e2:
                logger.warning(f"_transmit failed: {e2}")
                return None

    def get_uid(self) -> str | None:
        if not self.connect_card():
            return None
        try:
            result = self._transmit(
                [0xFF, 0xCA, 0x00, 0x00, 0x00]
            )
            if result and result[1] == 0x90:
                return "".join(
                    f"{b:02X}" for b in result[0]
                )
            return None
        except Exception:
            return None

    def is_card_present(self) -> bool:
        try:
            result = self._transmit(
                [0xFF, 0xCA, 0x00, 0x00, 0x00]
            )
            return result is not None and result[1] == 0x90
        except Exception:
            return False


# ══════════════════════════════════════════════════════════
#  Display helpers
# ══════════════════════════════════════════════════════════

def print_header(title: str):
    width = 25
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def print_section(title: str):
    print(f"\n{'─' * 20}")
    print(f"  {title}")
    print("─" * 20)


def print_ndef_preview(
    payload: bytes, data_type: str, data: str
):
    print_section("NDEF Preview")
    print(f"  Type    : {data_type.upper()}")
    print(
        f"  Content : "
        f"{data[:60]}{'...' if len(data) > 60 else ''}"
    )
    print(f"  Bytes   : {len(payload)}")
    print(
        f"  Hex     : {payload.hex().upper()[:64]}"
        f"{'...' if len(payload) > 32 else ''}"
    )
    pages = [
        payload[i:i+4].hex().upper()
        for i in range(0, len(payload), 4)
    ]
    print(
        f"  Pages({len(pages)}): "
        f"{' | '.join(pages[:6])}"
        f"{'...' if len(pages) > 6 else ''}"
    )


# ══════════════════════════════════════════════════════════
#  Card wait
# ══════════════════════════════════════════════════════════

def wait_for_card(
    reader: NFCReader, timeout: int = 60
) -> str | None:
    print("\n  Place card on reader...")
    print(f"  Timeout: {timeout}s")
    start = time.time()
    dots  = 0
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            print("\n\n  Timeout!")
            return None
        uid = reader.get_uid()
        if uid:
            print(f"\n\n  Card detected!")
            return uid
        dots = (dots + 1) % 4
        remaining = int(timeout - elapsed)
        print(
            f"\r  {'.' * dots}{' ' * (3-dots)} ({remaining}s)",
            end="", flush=True
        )
        time.sleep(0.2)


# ══════════════════════════════════════════════════════════
#  User input
# ══════════════════════════════════════════════════════════

def get_user_choice(prompt: str, valid: list) -> str:
    while True:
        ans = input(prompt).strip()
        if ans in valid:
            return ans
        print(f"  Invalid. Choose: {valid}")


def get_data_from_user() -> tuple | None:
    print_section("Choose Data Type")
    print("  1. URL  — website link")
    print("  2. TEXT — plain text")
    print("  0. Cancel")

    choice = get_user_choice(
        "\n  Choice (0-2): ", ["0", "1", "2"]
    )

    if choice == "0":
        return None

    if choice == "1":
        print(
            "\n  Examples: https://google.com | tel:9876543210"
        )
        while True:
            url = input("\n  URL: ").strip()
            if not url:
                print("  Cannot be empty!")
                continue
            if not any(
                url.lower().startswith(p)
                for p in [
                    "http://", "https://", "ftp://",
                    "tel:", "mailto:",
                ]
            ):
                ans = input(
                    f"  Add 'https://'? (y/n): "
                ).strip().lower()
                if ans == "y":
                    url = "https://" + url
            return "url", url

    elif choice == "2":
        print("\n  Example: Hello World")
        while True:
            text = input("\n  Text: ").strip()
            if not text:
                print("  Cannot be empty!")
                continue
            return "text", text

    return None


def ask_clear_first() -> bool:
    print_section("Clear card first?")
    print("  Y = Yes, clear old data")
    print("  N = No, write directly")
    ans = get_user_choice(
        "\n  Clear? (y/n): ", ["y", "n", "Y", "N"]
    )
    return ans.lower() == "y"

def main():
    print_header("ACR122U NFC Writer")

    # ── Reader ───────────────────────────────────────────
    print_section("Reader Connection")
    reader = NFCReader()
    try:
        reader.connect_reader()
    except Exception as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)

    # ── Wait for card ─────────────────────────────────────
    uid = wait_for_card(reader, timeout=20)
    if uid is None:
        sys.exit(0)

    print(f"\n  UID: {uid}")

    # ── Detect chip ───────────────────────────────────────
    print_section("Chip Detection")
    writer    = NFCWriter(reader)
    chip_info = writer.detect_chip()
    print()
    print(writer.get_chip_report())

    # ── DEBUG: MIFARE pe raw state dekho ─────────────────
    if chip_info.get("family") == "MIFARE":
        print_section("Card Debug State")
        writer.debug_card_state()

    # ── ATC ───────────────────────────────────────────────
    if chip_info.get("atc_supported"):
        print_section("ATC Counter")
        atc = writer.read_atc()
        if atc:
            print(f"  Count : {atc['count']}")
            print(f"  Hex   : 0x{atc['count_hex']}")
        else:
            print("  ATC not readable.")
    else:
        chip_type = chip_info.get("type", "UNKNOWN")
        if chip_type == "NTAG213":
            print("\n  ATC: NTAG213 has no counter.")
        elif chip_type in ("MIFARE_1K", "MIFARE_4K"):
            print("\n  ATC: MIFARE has no NFC counter.")

    # ── Writable check ────────────────────────────────────
    if not chip_info.get("writable", True):
        print("\n  Card locked — cannot write!")
        reader.disconnect_card()
        sys.exit(1)

    if chip_info.get("type") == "UNKNOWN":
        ans = get_user_choice(
            "\n  Unknown chip. Continue? (y/n): ",
            ["y", "n", "Y", "N"]
        )
        if ans.lower() == "n":
            sys.exit(0)

    # ── Data input ────────────────────────────────────────
    result = get_data_from_user()
    if result is None:
        print("\n  Cancelled.")
        reader.disconnect_card()
        sys.exit(0)

    data_type, data_content = result

    # ── NDEF Preview ──────────────────────────────────────
    try:
        preview_bytes = NDEFBuilder().build(
            data_content, data_type
        )
        print_ndef_preview(
            preview_bytes, data_type, data_content
        )

        max_bytes = chip_info.get("user_memory", 144)
        if len(preview_bytes) > max_bytes:
            print(
                f"\n  ERROR: Data too large! "
                f"{len(preview_bytes)}B > {max_bytes}B"
            )
            sys.exit(1)

        print(
            f"\n  Size OK: "
            f"{len(preview_bytes)} / {max_bytes} bytes"
        )

    except Exception as e:
        print(f"\n  Preview error: {e}")
        sys.exit(1)

    # ── Clear? ────────────────────────────────────────────
    do_clear = ask_clear_first()

    # ── Confirm ───────────────────────────────────────────
    print_section("Write Confirm")
    print(f"  UID        : {uid}")
    print(f"  Chip       : {chip_info.get('type', '?')}")
    print(f"  Type       : {data_type.upper()}")
    print(f"  Content    : {data_content[:60]}")
    print(f"  Bytes      : {len(preview_bytes)}")
    print(f"  Clear first: {'YES' if do_clear else 'NO'}")
    print()
    print("  Place card on reader!")
    print("  Do NOT remove during write!")
    input("\n  Press Enter to start...")

    # ── Reconnect ─────────────────────────────────────────
    print("\n  Reconnecting...")
    reader.disconnect_card()
    time.sleep(0.3)
    if not reader.connect_card():
        print("  Card not found! Place on reader.")
        sys.exit(1)
    print("  Connected OK")

    # ── Clear ─────────────────────────────────────────────
    if do_clear:
        print_section("Clearing Card")
        cleared = writer.clear()
        if not cleared:
            print("  Clear failed — continuing...")
        time.sleep(0.2)

    # ── Write ─────────────────────────────────────────────
    print_section("Writing to Card")
    try:
        if data_type == "url":
            success = writer.write_url(
                data_content, do_verify=True
            )
        elif data_type == "text":
            success = writer.write_text(
                data_content, do_verify=True
            )
        else:
            success = False

    except KeyboardInterrupt:
        print("\n\n  Interrupted!")
        success = False
    except Exception as e:
        print(f"\n  Error: {e}")
        logger.exception("Write error")
        success = False

    # ── DEBUG: Write ke baad state dekho ─────────────────
    if chip_info.get("family") == "MIFARE":
        print_section("Post-Write Debug")
        writer.debug_card_state()

    # ── Result ────────────────────────────────────────────
    print()
    if success:
        print("═" * 54)
        print("   WRITE SUCCESSFUL!")
        print("═" * 54)
        print(f"  UID     : {uid}")
        print(f"  Chip    : {chip_info.get('type','?')}")
        print(f"  Type    : {data_type.upper()}")
        print(f"  Content : {data_content[:50]}")
        print(f"  Bytes   : {len(preview_bytes)}")
        if data_type == "url":
            print("  Tap phone: browser will open")
        elif data_type == "text":
            print("  Tap phone: text will appear")
        print("═" * 54)
    else:
        print("═" * 54)
        print("   WRITE FAILED ")
        print("═" * 54)
        print("  Possible reasons:")
        print("    - Card removed during write")
        print("    - Card locked/write protected")
        print("    - Wrong card type")
        print("  → Try again with fresh card")
        print("═" * 54)

    reader.disconnect_card()
    print("\n  Remove card from reader.\n")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())