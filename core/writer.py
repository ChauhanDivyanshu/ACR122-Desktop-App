    # core/writer.py

import struct
import time
from loguru import logger

try:
    from .ndef_builder import NDEFBuilder
except ImportError:
    try:
        from core.ndef_builder import NDEFBuilder
    except ImportError:
        from ndef_builder import NDEFBuilder


MIFARE_KEY_A  = 0x60
MIFARE_KEY_B  = 0x61

FACTORY_KEY   = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
NDEF_MAD_KEY  = [0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5]
NDEF_DATA_KEY = [0xD3, 0xF7, 0xD3, 0xF7, 0xD3, 0xF7]
ZERO_KEY      = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

MIFARE_DEFAULT_KEYS = [
    FACTORY_KEY, ZERO_KEY, NDEF_MAD_KEY, NDEF_DATA_KEY,
    [0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5],
    [0x4D, 0x3A, 0x99, 0xC3, 0x51, 0xDD],
    [0x1A, 0x98, 0x2C, 0x7E, 0x45, 0x9A],
    [0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0],
]

# NFC Forum Standard Trailers
MAD_TRAILER = (
    NDEF_MAD_KEY + [0x78, 0x77, 0x88, 0xC1] + FACTORY_KEY
)
NDEF_TRAILER = (
    NDEF_DATA_KEY + [0x7F, 0x07, 0x88, 0x40] + FACTORY_KEY
)

# CC Block — E1 10 = Android ke liye required!
CC_BLOCK = [0xE1, 0x10, 0xE0, 0x00] + [0x00] * 12


def block_to_sector(block: int) -> int:
    return block // 4

def sector_trailer(sector: int) -> int:
    return sector * 4 + 3

def is_trailer(block: int) -> bool:
    return (block + 1) % 4 == 0

def calc_mad_crc(data: list) -> int:
    crc = 0xC7
    for byte in data:
        for _ in range(8):
            if (crc ^ byte) & 0x80:
                crc = ((crc << 1) ^ 0x1D) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
            byte = (byte << 1) & 0xFF
    return crc


class SectorInfo:
    __slots__ = (
        "read_key", "read_slot", "read_kt",
        "write_key", "write_slot", "write_kt",
        "writable", "write_tested",
    )
    def __init__(self, key, slot, kt):
        self.read_key     = key
        self.read_slot    = slot
        self.read_kt      = kt
        self.write_key    = key
        self.write_slot   = slot
        self.write_kt     = kt
        self.writable     = False
        self.write_tested = False


class NFCWriter:

    PAGE_DELAY   = 0.05
    VERIFY_DELAY = 0.5

    def __init__(self, reader):
        self.reader          = reader
        self.ndef            = NDEFBuilder()
        self._chip           = {}
        self._sectors:        dict[int, SectorInfo] = {}
        self._written_blocks: dict[int, list]       = {}

    # ══════════════════════════════════════════════════════
    #  DEBUG
    # ══════════════════════════════════════════════════════

    def debug_card_state(self):
        """Card ka raw state print karo — diagnose karo"""
        print("\n" + "═"*60)
        print("  MIFARE CARD DEBUG REPORT")
        print("═"*60)

        blocks_to_check = {
            0 : "Manufacturer",
            1 : "MAD1",
            2 : "MAD2",
            4 : "CC (Capability Container)",
            5 : "NDEF Data Block 1",
            6 : "NDEF Data Block 2",
            8 : "NDEF Data Block 3",
            9 : "NDEF Data Block 4",
            10: "NDEF Data Block 5",
        }

        for block, name in blocks_to_check.items():
            data = self._mifare_read_block(block)
            if data:
                hex_str = " ".join(f"{b:02X}" for b in data[:16])
                print(f"\n  Block {block:2d} [{name}]:")
                print(f"    {hex_str}")

                if block == 4:  # CC
                    print(f"    Magic  : 0x{data[0]:02X}", end="")
                    print(" " if data[0] == 0xE1 else "  WRONG! Need E1")
                    print(f"    Version: 0x{data[1]:02X}", end="")
                    print(" " if data[1] == 0x10 else
                          f"  WRONG! Need 0x10, got 0x{data[1]:02X}")
                    print(f"    Size   : 0x{data[2]:02X}")
                    print(f"    Access : 0x{data[3]:02X}", end="")
                    print("  R/W" if data[3] == 0x00 else "  WRONG!")

                if block == 5:  # NDEF
                    print(f"    TLV Tag: 0x{data[0]:02X}", end="")
                    print("  NDEF" if data[0] == 0x03 else
                          "  WRONG! Need 0x03")
                    print(f"    Length : {data[1]} bytes")
                    if data[1] == 0:
                        print("     EMPTY! Data not written here")
            else:
                print(f"\n  Block {block:2d} [{name}]:  CANNOT READ")

        print("\n" + "─"*60)
        print("  SECTOR MAP:")
        for s in range(8):
            info = self._sectors.get(s)
            if info:
                print(
                    f"  Sec {s}: "
                    f"key={bytes(info.read_key).hex().upper()} "
                    f"kt={'A' if info.read_kt==0x60 else 'B'} "
                    f"writable={info.writable}"
                )
            else:
                print(f"  Sec {s}:  NOT FOUND")
        print("═"*60)

    # ══════════════════════════════════════════════════════
    #  CHIP DETECTION
    # ══════════════════════════════════════════════════════

    def detect_chip(self) -> dict:
        info = {
            "type": "UNKNOWN", "family": "UNKNOWN",
            "chip_id": "", "uid_length": 0,
            "start_page": 4, "end_page": 39,
            "user_pages": 35, "memory": 140,
            "user_memory": 140, "writable": True,
            "atc_supported": False, "atc_page": None,
            "lock_bytes": [], "ndef_formatted": False,
            "format_possible": False, "card_status": "unknown",
        }

        uid_bytes = self._get_uid_bytes()
        if uid_bytes:
            info["chip_id"]    = "".join(f"{b:02X}" for b in uid_bytes)
            info["uid_length"] = len(uid_bytes)
            logger.debug(f"UID={info['chip_id']}")

        uid_len = info["uid_length"]

        if uid_len == 4:
            if self._try_detect_mifare(info):
                self._chip = info
                return info
        elif uid_len == 7:
            if self._try_detect_ntag(info):
                self._chip = info
                return info
            if self._try_detect_mifare(info):
                self._chip = info
                return info
        else:
            if self._try_detect_mifare(info):
                self._chip = info
                return info
            if self._try_detect_ntag(info):
                self._chip = info
                return info

        self._chip = info
        return info

    def _try_detect_ntag(self, info: dict) -> bool:
        cc = self._read_ntag_page(3)
        if not cc or len(cc) < 4 or cc[0] != 0xE1:
            return False
        ntag_map = {
            0x12: ("NTAG213", 144,  35, 4,  38, False, None),
            #0x3E: ("NTAG215", 504, 126, 4, 129, True,  41),
            0x6D: ("NTAG216", 888, 222, 4, 225, True,  41),
        }
        sc = cc[2]
        if sc not in ntag_map:
            return False
        name, mem, pages, start, end, atc, atc_page = ntag_map[sc]
        info.update({
            "type": name, "family": "NTAG",
            "memory": mem, "user_memory": mem,
            "user_pages": pages,
            "start_page": start, "end_page": end,
            "atc_supported": atc, "atc_page": atc_page,
            "writable": cc[3] != 0x0F,
            "ndef_formatted": True,
            "format_possible": False,
            "card_status": "ready",
        })
        logger.info(f"NTAG: {name}")
        return True

    def _try_detect_mifare(self, info: dict) -> bool:
        probe = self._probe_any_sector()
        if not probe:
            return False

        mem           = self._get_mifare_memory_info(*probe)
        total_sectors = 16 if mem["type"] == "MIFARE_1K" else 40

        info.update({
            "type": mem["type"], "family": "MIFARE",
            "memory": mem["total_memory"],
            "user_memory": mem["user_memory"],
            "user_pages": mem["user_blocks"],
            "start_page": 1,
            "end_page": mem["last_user_block"],
            "atc_supported": False, "atc_page": None,
            "writable": True,
        })

        print(f"\n  Scanning {total_sectors} sectors...")
        self._build_sector_key_map(total_sectors, hint=probe)

        acc = len(self._sectors)
        wr  = sum(1 for s in self._sectors.values() if s.writable)
        print(f"  Sectors: {acc}/{total_sectors} | {wr} writable")

        self._analyze_card_status(info)
        return True

    def _analyze_card_status(self, info: dict):
        total  = 16 if info.get("type") == "MIFARE_1K" else 40
        wr_cnt = sum(1 for s in self._sectors.values() if s.writable)

        # CC Block check
        ndef_formatted = False
        data4 = self._mifare_read_block(4)
        logger.debug(
            f"CC block4: "
            f"{bytes(data4).hex().upper() if data4 else 'FAIL'}"
        )
        if data4 and data4[0] == 0xE1 and data4[1] in (0x10, 0x03):
            ndef_formatted = True

        info["ndef_formatted"]  = ndef_formatted
        info["format_possible"] = (
            self._sectors.get(0) is not None
            and self._sectors[0].writable
        )

        if ndef_formatted:
            status = "ndef_ready"
            print("  Status: NDEF Ready ")
        elif wr_cnt == total:
            status = "factory_blank"
            print("  Status: Factory Blank ")
        elif wr_cnt == 0:
            status = "write_protected"
            print("  Status: Write Protected ")
        else:
            status = "partial"
            print(f"  Status: Partial ({wr_cnt}/{total})")

        info["card_status"] = status

    # ══════════════════════════════════════════════════════
    #  SECTOR KEY MAP
    # ══════════════════════════════════════════════════════

    def _probe_any_sector(self):
        attempts = [
            (NDEF_DATA_KEY, MIFARE_KEY_A),
            (NDEF_MAD_KEY,  MIFARE_KEY_A),
            (FACTORY_KEY,   MIFARE_KEY_A),
            (ZERO_KEY,      MIFARE_KEY_A),
            (FACTORY_KEY,   MIFARE_KEY_B),
        ] + [(k, MIFARE_KEY_A) for k in MIFARE_DEFAULT_KEYS]

        for key, kt in attempts:
            for slot in [0x00, 0x01]:
                if not self._load_key(key, slot):
                    continue
                for block in [4, 1, 8, 12]:
                    if self._raw_auth(block, kt, slot):
                        logger.info(
                            f"Probe: {bytes(key).hex().upper()} "
                            f"b={block} kt={'A' if kt==MIFARE_KEY_A else 'B'}"
                        )
                        return (key, slot, kt)
        return None

    def _build_sector_key_map(self, total_sectors: int, hint=None):
        self._sectors = {}
        hint_key  = hint[0] if hint else FACTORY_KEY
        hint_slot = hint[1] if hint else 0x00
        hint_kt   = hint[2] if hint else MIFARE_KEY_A

        for sector in range(total_sectors):
            trailer  = sector_trailer(sector)
            ndef_key = NDEF_MAD_KEY if sector == 0 else NDEF_DATA_KEY
            info     = None

            key_order = [
                (ndef_key,    MIFARE_KEY_A, 0x00),
                (FACTORY_KEY, MIFARE_KEY_A, 0x00),
                (ZERO_KEY,    MIFARE_KEY_A, 0x00),
                (hint_key,    MIFARE_KEY_A, hint_slot),
                (hint_key,    hint_kt,      hint_slot),
                (FACTORY_KEY, MIFARE_KEY_B, 0x00),
                (ZERO_KEY,    MIFARE_KEY_B, 0x00),
            ] + [(k, MIFARE_KEY_A, 0x00) for k in MIFARE_DEFAULT_KEYS]

            for key, kt, slot in key_order:
                if key is None:
                    continue
                if self._load_key(key, slot):
                    if self._raw_auth(trailer, kt, slot):
                        info = SectorInfo(key, slot, kt)
                        break

            if info is None:
                logger.warning(f"Sector {sector}: no key")
                continue

            self._sectors[sector] = info
            self._test_write(sector, info)

    def _test_write(self, sector: int, info: SectorInfo):
        test_block = 1 if sector == 0 else sector * 4

        if test_block == 0 or is_trailer(test_block):
            info.writable = False
            info.write_tested = True
            return

        if not self._load_key(info.read_key, info.read_slot):
            info.writable = False
            info.write_tested = True
            return
        if not self._raw_auth(test_block, info.read_kt, info.read_slot):
            info.writable = False
            info.write_tested = True
            return

        r       = self.reader._transmit([0xFF, 0xB0, 0x00, test_block, 0x10])
        current = (
            list(r[0][:16])
            if (r and r[1] == 0x90 and len(r[0]) >= 16)
            else [0x00] * 16
        )

        if not self._load_key(info.read_key, info.read_slot):
            info.writable = False
            info.write_tested = True
            return
        if not self._raw_auth(test_block, info.read_kt, info.read_slot):
            info.writable = False
            info.write_tested = True
            return

        r2 = self.reader._transmit(
            [0xFF, 0xD6, 0x00, test_block, 0x10] + current
        )
        ok = bool(r2 and r2[1] == 0x90)
        info.writable     = ok
        info.write_tested = True
        if ok:
            info.write_key  = info.read_key
            info.write_slot = info.read_slot
            info.write_kt   = info.read_kt

    def _get_mifare_memory_info(self, key, slot, kt) -> dict:
        self._load_key(key, slot)
        if self._raw_auth(64, kt, slot):
            return {
                "type": "MIFARE_4K", "total_memory": 4096,
                "user_memory": 3440, "user_blocks": 215,
                "last_user_block": 254,
            }
        return {
            "type": "MIFARE_1K", "total_memory": 1024,
            "user_memory": 752, "user_blocks": 47,
            "last_user_block": 62,
        }

    def rebuild_key_map(self):
        if self._chip.get("family") != "MIFARE":
            return
        total        = 16 if self._chip.get("type") == "MIFARE_1K" else 40
        old_writable = {s: i.writable for s, i in self._sectors.items()}

        if self._chip.get("ndef_formatted"):
            new_sectors = {}
            for sector in range(total):
                trailer = sector_trailer(sector)
                key     = NDEF_MAD_KEY if sector == 0 else NDEF_DATA_KEY
                if self._load_key(key, 0x00):
                    if self._raw_auth(trailer, MIFARE_KEY_A, 0x00):
                        si              = SectorInfo(key, 0x00, MIFARE_KEY_A)
                        si.write_key    = key
                        si.write_slot   = 0x00
                        si.write_kt     = MIFARE_KEY_A
                        si.writable     = old_writable.get(sector, True)
                        si.write_tested = True
                        new_sectors[sector] = si
                        continue
                for fk, fkt in [
                    (FACTORY_KEY, MIFARE_KEY_A),
                    (ZERO_KEY,    MIFARE_KEY_A),
                ]:
                    if self._load_key(fk, 0x00):
                        if self._raw_auth(trailer, fkt, 0x00):
                            si              = SectorInfo(fk, 0x00, fkt)
                            si.write_key    = fk
                            si.write_slot   = 0x00
                            si.write_kt     = fkt
                            si.writable     = old_writable.get(sector, False)
                            si.write_tested = True
                            new_sectors[sector] = si
                            break
            self._sectors = new_sectors
        else:
            probe = self._probe_any_sector()
            if probe:
                self._build_sector_key_map(total, hint=probe)
            for s, i in self._sectors.items():
                if s in old_writable:
                    i.writable = old_writable[s]

        logger.info(f"Rebuild: {len(self._sectors)}/{total}")

    # ══════════════════════════════════════════════════════
    #  FORMAT
    # ══════════════════════════════════════════════════════

    def format_mifare_ndef(self) -> bool:
        """
        CORRECT ORDER:
          1. Sectors 1-15 trailers  (factory key)
          2. CC block 4             (NDEF data key)
          3. Empty NDEF block 5     (NDEF data key)
          4. MAD blocks 1,2         (factory key — sector 0 not yet changed)
          5. Sector 0 trailer       (LAST — key change)
        """
        chip_type     = self._chip.get("type", "MIFARE_1K")
        total_sectors = 16 if chip_type == "MIFARE_1K" else 40

        print("\n  " + "═"*50)
        print("  MIFARE NDEF FORMAT")
        print("  " + "═"*50)

        wr = sum(1 for s in self._sectors.values() if s.writable)
        if wr == 0:
            print("  ✗ No writable sectors!")
            self._print_write_protection_help()
            return False

        results = {
            "trailers": 0, "cc": False,
            "empty_ndef": False, "mad1": False,
            "mad2": False, "s0_trailer": False,
        }

        # ── 1. Data Sector Trailers ───────────────────────
        print(f"\n  [1/5] Data trailers (sectors 1-{total_sectors-1})...")
        ok_count = 0
        for sector in range(1, total_sectors):
            ok = self._write_trailer(sector, NDEF_TRAILER)
            if ok:
                ok_count += 1
                si              = SectorInfo(NDEF_DATA_KEY, 0x00, MIFARE_KEY_A)
                si.write_key    = NDEF_DATA_KEY
                si.write_slot   = 0x00
                si.write_kt     = MIFARE_KEY_A
                si.writable     = True
                si.write_tested = True
                self._sectors[sector] = si
            print(
                f"\r        Sec {sector:2d}: {'' if ok else ''}  ",
                end="", flush=True
            )
            time.sleep(0.02)
        results["trailers"] = ok_count
        print(f"\n        {ok_count}/{total_sectors-1} done")

        # ── 2. CC Block ───────────────────────────────────
        print(f"\n  [2/5] CC block (block 4) → E1 10 E0 00...")
        cc_ok = False
        for key in [NDEF_DATA_KEY, FACTORY_KEY, ZERO_KEY]:
            cc_ok = self._write_block_direct(
                4, CC_BLOCK, key, 0x00, MIFARE_KEY_A
            )
            if cc_ok:
                break
            cc_ok = self._write_block_direct(
                4, CC_BLOCK, key, 0x00, MIFARE_KEY_B
            )
            if cc_ok:
                break

        results["cc"] = cc_ok

        # Verify CC
        if cc_ok:
            time.sleep(0.05)
            v = self._mifare_read_block(4)
            if v:
                ok_str = "" if (v[0] == 0xE1 and v[1] == 0x10) else "WRONG!"
                print(f"        {ok_str} [{' '.join(f'{b:02X}' for b in v[:4])}]")
            else:
                print("         written")
        else:
            print("         FAILED")

        # ── 3. Empty NDEF ─────────────────────────────────
        print(f"\n  [3/5] Empty NDEF TLV (block 5)...")
        empty = [0x03, 0x00, 0xFE, 0x00] + [0x00] * 12
        ndef_ok = False
        for key in [NDEF_DATA_KEY, FACTORY_KEY]:
            ndef_ok = self._write_block_direct(
                5, empty, key, 0x00, MIFARE_KEY_A
            )
            if ndef_ok:
                break
        results["empty_ndef"] = ndef_ok
        print(f"        {'' if ndef_ok else ''}")

        # ── 4. MAD Blocks ─────────────────────────────────
        # IMPORTANT: Sector 0 trailer ABHI NAHI BADLA
        # isliye factory key se likho
        print(f"\n  [4/5] MAD blocks (1 & 2, sector 0)...")

        mad1    = [0x00] * 16
        mad1[1] = 0x01  # Info: MAD v1
        for s in range(1, 8):
            idx          = 2 + (s - 1) * 2
            mad1[idx]     = 0x03
            mad1[idx + 1] = 0xE1
        mad1[0] = calc_mad_crc(mad1[1:])

        mad2 = [0x00] * 16
        for s in range(8, 16):
            idx          = (s - 8) * 2
            mad2[idx]     = 0x03
            mad2[idx + 1] = 0xE1

        logger.debug(f"MAD1: {bytes(mad1).hex().upper()}")
        logger.debug(f"MAD2: {bytes(mad2).hex().upper()}")

        mad1_ok = False
        mad2_ok = False
        # Sector 0 key abhi factory hai!
        for key in [FACTORY_KEY, ZERO_KEY, NDEF_MAD_KEY]:
            if not mad1_ok:
                mad1_ok = self._write_block_direct(
                    1, mad1, key, 0x00, MIFARE_KEY_A
                )
            if not mad2_ok:
                mad2_ok = self._write_block_direct(
                    2, mad2, key, 0x00, MIFARE_KEY_A
                )
            if mad1_ok and mad2_ok:
                break

        results["mad1"] = mad1_ok
        results["mad2"] = mad2_ok
        print(
            f"        MAD1: {'' if mad1_ok else ''} | "
            f"MAD2: {'' if mad2_ok else ''}"
        )

        # ── 5. Sector 0 Trailer — LAST! ───────────────────
        print(f"\n  [5/5] Sector 0 trailer (LAST — key change)...")
        s0_ok = self._write_trailer(0, MAD_TRAILER)
        if s0_ok:
            si              = SectorInfo(NDEF_MAD_KEY, 0x00, MIFARE_KEY_A)
            si.write_key    = NDEF_MAD_KEY
            si.write_slot   = 0x00
            si.write_kt     = MIFARE_KEY_A
            si.writable     = True
            si.write_tested = True
            self._sectors[0] = si
            print("         MAD Key A set")
        else:
            print("         (may be ok if already set)")

        results["s0_trailer"] = s0_ok

        # ── Summary ───────────────────────────────────────
        print("\n  " + "─"*50)
        print("  FORMAT SUMMARY:")
        print(f"    [1] Data trailers: {results['trailers']}/{total_sectors-1}")
        print(f"    [2] CC (block 4) : {'' if results['cc'] else ''}")
        print(f"    [3] Empty NDEF   : {'' if results['empty_ndef'] else ''}")
        print(f"    [4] MAD1 (blk 1): {'' if results['mad1'] else ''}")
        print(f"    [4] MAD2 (blk 2): {'' if results['mad2'] else ''}")
        print(f"    [5] S0 trailer  : {'' if results['s0_trailer'] else ''}")

        success = results["cc"] and results["trailers"] >= 1
        if success:
            self._chip["ndef_formatted"] = True
            self._chip["card_status"]    = "ndef_ready"
            locked = total_sectors - 1 - results["trailers"]
            print("\n   FORMAT SUCCESS!")
            print("  Card is now Android/GoToTags readable!")
            if locked:
                print(f"  NOTE: {locked} sectors locked")
            return True
        else:
            print("\n   FORMAT FAILED!")
            self._print_write_protection_help()
            return False

    def _write_trailer(self, sector: int, trailer: list) -> bool:
        trailer_block                          = sector_trailer(sector)
        auth_key, auth_slot, auth_kt = None, 0x00, MIFARE_KEY_A

        sinfo = self._sectors.get(sector)
        if sinfo:
            if self._load_key(sinfo.read_key, sinfo.read_slot):
                if self._raw_auth(
                    trailer_block, sinfo.read_kt, sinfo.read_slot
                ):
                    auth_key  = sinfo.read_key
                    auth_slot = sinfo.read_slot
                    auth_kt   = sinfo.read_kt

        if auth_key is None:
            all_keys = [
                (FACTORY_KEY,   MIFARE_KEY_A, 0x00),
                (NDEF_MAD_KEY,  MIFARE_KEY_A, 0x00),
                (NDEF_DATA_KEY, MIFARE_KEY_A, 0x00),
                (ZERO_KEY,      MIFARE_KEY_A, 0x00),
                (FACTORY_KEY,   MIFARE_KEY_B, 0x00),
                (ZERO_KEY,      MIFARE_KEY_B, 0x00),
                (FACTORY_KEY,   MIFARE_KEY_A, 0x01),
            ] + [(k, MIFARE_KEY_A, 0x00) for k in MIFARE_DEFAULT_KEYS]

            for key, kt, slot in all_keys:
                if self._load_key(key, slot):
                    if self._raw_auth(trailer_block, kt, slot):
                        auth_key, auth_slot, auth_kt = key, slot, kt
                        break

        if auth_key is None:
            logger.warning(f"Sector {sector} trailer: no auth")
            return False

        if not self._load_key(auth_key, auth_slot):
            return False
        if not self._raw_auth(trailer_block, auth_kt, auth_slot):
            return False

        data = (list(trailer) + [0x00] * 16)[:16]
        r    = self.reader._transmit(
            [0xFF, 0xD6, 0x00, trailer_block, 0x10] + data
        )
        ok = bool(r and r[1] == 0x90)
        if not ok:
            sw = f"SW={r[1]:02X}{r[2]:02X}" if r else "no resp"
            logger.warning(f"Sec {sector} trailer fail: {sw}")
        return ok

    def _write_block_direct(self, block: int, data: list,
                             key: list, slot: int, kt: int) -> bool:
        if block == 0 or is_trailer(block):
            return False
        if not self._load_key(key, slot):
            return False
        if not self._raw_auth(block, kt, slot):
            return False
        data16 = (list(data) + [0x00] * 16)[:16]
        r = self.reader._transmit(
            [0xFF, 0xD6, 0x00, block, 0x10] + data16
        )
        ok = bool(r and r[1] == 0x90)
        if ok:
            logger.debug(
                f"Block {block}  [{bytes(key).hex().upper()}]"
            )
        return ok

    def _print_write_protection_help(self):
        print("\n  ╔══════════════════════════════════════════╗")
        print("  ║  Use fresh MIFARE 1K (factory key FF...) ║")
        print("  ║  or NTAG213/215/216                      ║")
        print("  ╚══════════════════════════════════════════╝")

    # ══════════════════════════════════════════════════════
    #  WRITE API
    # ══════════════════════════════════════════════════════

    def write_url(self, url: str, do_verify: bool = True) -> bool:
        payload = self.ndef.build(url, "url")
        logger.info(
            f"write_url: {len(payload)}B → {payload.hex().upper()}"
        )
        return self._write_ndef_payload(payload, do_verify)

    def write_text(self, text: str, do_verify: bool = True) -> bool:
        payload = self.ndef.build(text, "text")
        logger.info(
            f"write_text: {len(payload)}B → {payload.hex().upper()}"
        )
        return self._write_ndef_payload(payload, do_verify)

    def write_raw(self, hex_str: str, do_verify: bool = True) -> bool:
        payload = self.ndef.build(hex_str, "raw")
        return self._write_ndef_payload(payload, do_verify)

    def _write_ndef_payload(self, payload: bytes,
                             do_verify: bool) -> bool:
        if self._chip.get("family") == "MIFARE":
            return self._write_ndef_mifare(payload, do_verify)
        return self._write_ndef_ntag(payload, do_verify)

    def _write_ndef_ntag(self, payload: bytes,
                          do_verify: bool) -> bool:
        start = self._chip.get("start_page", 4)
        pages = self.ndef.to_pages_ntag(payload, start)
        total = len(pages)
        print(f"\n  NTAG: {total} pages ({len(payload)}B)...")

        for idx, (page_num, chunk) in enumerate(pages):
            if not self.reader.is_card_present():
                print("\n  Card removed!")
                return False
            ok  = self._ntag_write_page(page_num, chunk)
            pct = int((idx + 1) / total * 100)
            print(
                f"\r  Page {page_num:3d} | "
                f"{bytes(chunk).hex().upper()} | "
                f"{'OK  ' if ok else 'FAIL'} | {pct:3d}%",
                end="", flush=True
            )
            if not ok:
                return False
            time.sleep(self.PAGE_DELAY)

        print("\n  All pages written.")
        if do_verify:
            time.sleep(self.VERIFY_DELAY)
            return self._verify_ntag(payload, start)
        return True

    def _write_ndef_mifare(self, payload: bytes,
                            do_verify: bool) -> bool:
        # Auto-format if needed
        if not self._chip.get("ndef_formatted"):
            if self._chip.get("card_status") == "write_protected":
                print("\n   Write protected!")
                self._print_write_protection_help()
                return False
            print("\n  Auto-formatting for NDEF...")
            if not self.format_mifare_ndef():
                return False
            time.sleep(0.5)
            self.rebuild_key_map()

        # Available blocks: 5+ skip trailers and reserved
        reserved  = {0, 1, 2, 3, 4}
        end_block = self._chip.get("end_page", 62)
        avail     = []

        for b in range(5, end_block + 1):
            if is_trailer(b) or b in reserved:
                continue
            sector = block_to_sector(b)
            sinfo  = self._sectors.get(sector)
            if sinfo and sinfo.writable:
                avail.append(b)

        # Split into 16-byte chunks
        pad    = (16 - len(payload) % 16) % 16
        data   = payload + bytes(pad)
        chunks = [
            list(data[i:i+16])
            for i in range(0, len(data), 16)
        ]
        total = len(chunks)

        logger.info(
            f"MIFARE write: {len(payload)}B → "
            f"{len(data)}B → {total} blocks"
        )
        logger.info(f"Payload: {payload.hex().upper()}")

        if not avail:
            print("\n   No writable blocks!")
            return False
        if total > len(avail):
            print(
                f"\n   Not enough space! "
                f"Need={total} Have={len(avail)}"
            )
            return False

        print(
            f"\n  MIFARE NDEF: {total} blocks "
            f"({len(payload)}B)..."
        )
        print(f"  Blocks: {avail[:total]}")

        self._written_blocks = {}
        written = 0

        for chunk16, block in zip(chunks, avail):
            if not self.reader.is_card_present():
                print("\n  Card removed!")
                return False

            ok      = self._mifare_write_block(block, chunk16)
            written += 1
            pct     = int(written / total * 100)

            print(
                f"\r  Block {block:3d} "
                f"(Sec {block_to_sector(block)}) | "
                f"{bytes(chunk16).hex().upper()} | "
                f"{'OK  ' if ok else 'FAIL'} | {pct:3d}%",
                end="", flush=True
            )

            if not ok:
                print(f"\n   FAILED at block {block}")
                return False

            self._written_blocks[block] = chunk16
            time.sleep(self.PAGE_DELAY)

        print(f"\n   {written}/{total} blocks written")

        if do_verify:
            time.sleep(self.VERIFY_DELAY)
            return self._verify_mifare_written_blocks()
        return True

    # ══════════════════════════════════════════════════════
    #  READ
    # ══════════════════════════════════════════════════════

    def read_card(self) -> dict:
        if self._chip.get("family") == "MIFARE":
            return self._read_ndef_mifare()
        return self._read_ndef_ntag()

    def _read_ndef_ntag(self) -> dict:
        start     = self._chip.get("start_page", 4)
        chip_type = self._chip.get("type", "NTAG213")
        raw       = []
        for page in range(start, start + 32):
            data = self._read_ntag_page(page)
            if data is None:
                break
            raw.extend(data)
            if 0xFE in data:
                break
        result              = self.ndef.decode(bytes(raw), chip_type)
        result["uid"]       = self._chip.get("chip_id", "")
        result["card_type"] = chip_type
        return result

    def _read_ndef_mifare(self) -> dict:
        chip_type = self._chip.get("type", "MIFARE_1K")
        if not self._chip.get("ndef_formatted"):
            return {
                "type": "not_formatted",
                "data": "Card not NDEF formatted",
                "uid": self._chip.get("chip_id", ""),
                "card_type": chip_type,
            }

        reserved = {0, 1, 2, 3, 4}
        end_blk  = self._chip.get("end_page", 62)
        raw      = bytearray()

        for block in range(5, end_blk + 1):
            if is_trailer(block) or block in reserved:
                continue
            data = self._mifare_read_block(block)
            if data is None:
                continue
            raw.extend(data[:16])
            if 0xFE in data:
                break

        logger.debug(
            f"MIFARE read: {bytes(raw[:32]).hex().upper()}"
        )
        result              = self.ndef.decode(bytes(raw), chip_type)
        result["uid"]       = self._chip.get("chip_id", "")
        result["card_type"] = chip_type
        return result

    # ══════════════════════════════════════════════════════
    #  CLEAR
    # ══════════════════════════════════════════════════════

    def clear(self) -> bool:
        family = self._chip.get("family", "NTAG")
        failed = 0

        if family == "MIFARE":
            end_blk  = self._chip.get("end_page", 62)
            reserved = {0, 1, 2, 3}
            blocks   = [
                b for b in range(4, end_blk + 1)
                if not is_trailer(b) and b not in reserved
            ]
            print(f"\n  Clearing {len(blocks)} blocks...")
            for block in blocks:
                if not self.reader.is_card_present():
                    return False
                if not self._mifare_write_block(block, [0x00] * 16):
                    failed += 1
                time.sleep(0.02)

            # Restore CC + empty NDEF
            if self._chip.get("ndef_formatted"):
                self._write_block_direct(
                    4, CC_BLOCK, NDEF_DATA_KEY, 0x00, MIFARE_KEY_A
                )
                empty = [0x03, 0x00, 0xFE, 0x00] + [0x00] * 12
                self._write_block_direct(
                    5, empty, NDEF_DATA_KEY, 0x00, MIFARE_KEY_A
                )
        else:
            start = self._chip.get("start_page", 4)
            end   = self._chip.get("end_page", 38)
            print(f"\n  Clearing pages {start}–{end}...")
            for page in range(start, end + 1):
                if not self.reader.is_card_present():
                    return False
                if not self._ntag_write_page(page, [0x00] * 4):
                    failed += 1
                time.sleep(0.02)

        print(f"  Clear done. ({failed} failed)")
        return True

    # ══════════════════════════════════════════════════════
    #  VERIFY
    # ══════════════════════════════════════════════════════

    def _verify_ntag(self, payload: bytes,
                     start_page: int = 4) -> bool:
        print("\n  Verifying...")
        self.reader.disconnect_card()
        time.sleep(0.5)
        self.reader.connect_card()
        time.sleep(0.3)
        for page_num, exp in self.ndef.to_pages_ntag(
            payload, start_page
        ):
            got = self._read_ntag_page(page_num)
            if not got or list(got[:4]) != list(exp):
                print(f"  ✗ MISMATCH page {page_num}")
                return False
        print("   Verify OK!")
        return True

    def _verify_mifare_written_blocks(self) -> bool:
        if not self._written_blocks:
            return False
        print(
            f"\n  Verifying "
            f"{len(self._written_blocks)} blocks..."
        )
        self.reader.disconnect_card()
        time.sleep(0.5)
        self.reader.connect_card()
        time.sleep(0.3)
        self.rebuild_key_map()

        all_ok = True
        for blk, exp in self._written_blocks.items():
            got = self._mifare_read_block(blk)
            if got is None:
                print(f"   Cannot read block {blk}")
                all_ok = False
            elif list(got[:16]) != list(exp):
                print(
                    f"   Mismatch block {blk}\n"
                    f"    exp: {bytes(exp).hex().upper()}\n"
                    f"    got: {bytes(got[:16]).hex().upper()}"
                )
                all_ok = False

        print(
            "   Verify OK!"
            if all_ok else "   Verify FAILED"
        )
        return all_ok

    def verify(self, payload: bytes, start_page: int = 4) -> bool:
        if self._chip.get("family") == "MIFARE":
            return self._verify_mifare_written_blocks()
        return self._verify_ntag(payload, start_page)

    # ══════════════════════════════════════════════════════
    #  CHIP REPORT
    # ══════════════════════════════════════════════════════

    def get_chip_report(self) -> str:
        c      = self._chip
        family = c.get("family", "UNKNOWN")

        if family == "MIFARE":
            total_s = 16 if c.get("type") == "MIFARE_1K" else 40
            acc     = len(self._sectors)
            wr      = sum(
                1 for s in self._sectors.values()
                if s.writable
            )
            mem_str = (
                f"{c.get('memory','?')}B / "
                f"{c.get('user_memory','?')}B usable"
            )
            layout  = (
                f"Blocks {c.get('start_page')}–"
                f"{c.get('end_page')}"
            )
            sec_str = f"{acc}/{total_s}, {wr} writable"
            status_map = {
                "ndef_ready"     : "NDEF Ready ",
                "factory_blank"  : "Factory Blank ",
                "write_protected": "Write Protected ",
                "partial"        : "Partial ",
                "unknown"        : "Unknown",
            }
            status_str = status_map.get(
                c.get("card_status", ""), "?"
            )
            fmt_str = (
                "YES  (Android readable)"
                if c.get("ndef_formatted")
                else (
                    "NO — auto-format on write"
                    if c.get("format_possible")
                    else "NO — write protected"
                )
            )
        else:
            mem_str    = f"{c.get('memory','?')} bytes"
            layout     = (
                f"Pages {c.get('start_page')}–"
                f"{c.get('end_page')}"
            )
            sec_str    = None
            status_str = "NTAG ready "
            fmt_str    = "YES  (NTAG native)"

        lines = [
            "┌──────────────────────────────────────────────┐",
            "│             CHIP INFORMATION                 │",
            "├──────────────────────────────────────────────┤",
            f"│  Type     : {c.get('type','?'):<33}│",
            f"│  Family   : {family:<33}│",
            f"│  UID      : {c.get('chip_id','?'):<33}│",
            f"│  Memory   : {mem_str:<33}│",
            f"│  Layout   : {layout:<33}│",
            f"│  Status   : {status_str:<33}│",
            f"│  NDEF     : {fmt_str:<33}│",
            f"│  ATC      : "
            f"{'YES' if c.get('atc_supported') else 'NO':<33}│",
        ]
        if sec_str:
            lines.append(f"│  Sectors  : {sec_str:<33}│")
        lines.append(
            "└──────────────────────────────────────────────┘"
        )
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════
    #  LOW-LEVEL
    # ══════════════════════════════════════════════════════

    def _load_key(self, key: list, slot: int) -> bool:
        r = self.reader._transmit(
            [0xFF, 0x82, 0x00, slot, 0x06] + list(key)
        )
        return bool(r and r[1] == 0x90)

    def _raw_auth(self, block: int, kt: int,
                  slot: int) -> bool:
        r = self.reader._transmit(
            [0xFF, 0x86, 0x00, 0x00, 0x05,
             0x01, 0x00, block, kt, slot]
        )
        return bool(r and r[1] == 0x90)

    def _auth_for_read(self, block: int) -> bool:
        sector = block_to_sector(block)
        info   = self._sectors.get(sector)
        if not info:
            return False
        if not self._load_key(info.read_key, info.read_slot):
            return False
        return self._raw_auth(
            block, info.read_kt, info.read_slot
        )

    def _auth_for_write(self, block: int) -> bool:
        sector = block_to_sector(block)
        info   = self._sectors.get(sector)
        if not info or not info.writable:
            return False
        if not self._load_key(
            info.write_key, info.write_slot
        ):
            return False
        return self._raw_auth(
            block, info.write_kt, info.write_slot
        )

    def _mifare_read_block(self, block: int) -> list | None:
        if not self._auth_for_read(block):
            return None
        r = self.reader._transmit(
            [0xFF, 0xB0, 0x00, block, 0x10]
        )
        if r and r[1] == 0x90 and len(r[0]) >= 16:
            return list(r[0][:16])
        return None

    def _mifare_write_block(self, block: int,
                             data16: list) -> bool:
        if block == 0 or is_trailer(block):
            return True
        sector = block_to_sector(block)
        info   = self._sectors.get(sector)
        if not info or not info.writable:
            logger.warning(f"Block {block}: not writable")
            return False
        if not self._load_key(
            info.write_key, info.write_slot
        ):
            return False
        if not self._raw_auth(
            block, info.write_kt, info.write_slot
        ):
            return False
        data16 = (list(data16) + [0] * 16)[:16]
        r = self.reader._transmit(
            [0xFF, 0xD6, 0x00, block, 0x10] + data16
        )
        ok = bool(r and r[1] == 0x90)
        if not ok:
            sw = f"SW={r[1]:02X}{r[2]:02X}" if r else "no resp"
            logger.warning(f"Block {block} fail: {sw}")
        return ok

    def _ntag_cmd(self, cmd: list) -> list:
        inner = [0xD4, 0x40, 0x01] + cmd
        return [
            0xFF, 0x00, 0x00, 0x00, len(inner)
        ] + inner

    def _read_ntag_page(self, page: int) -> list | None:
        cmd = self._ntag_cmd([0x30, page])
        r   = self.reader._transmit(cmd)
        if r and r[1] == 0x90:
            resp = r[0]
            if (len(resp) >= 7 and resp[0] == 0xD5
                    and resp[1] == 0x41
                    and resp[2] == 0x00):
                return list(resp[3:7])
            if len(resp) >= 4:
                return list(resp[:4])
        r = self.reader._transmit(
            [0xFF, 0xB0, 0x00, page, 0x10]
        )
        if r and r[1] == 0x90 and len(r[0]) >= 4:
            return list(r[0][:4])
        return None

    def _ntag_write_page(self, page: int,
                          data: list) -> bool:
        data   = (list(data) + [0, 0, 0, 0])[:4]
        cmd    = self._ntag_cmd([0xA2, page] + data)
        result = self.reader._transmit(cmd)
        if not result:
            return False
        if result[1] == 0x90:
            return True
        resp = result[0]
        if resp and len(resp) >= 3:
            if (resp[0] == 0xD5 and resp[1] == 0x41
                    and resp[2] == 0x00):
                return True
        return False

    def _get_uid_bytes(self) -> list | None:
        r = self.reader._transmit(
            [0xFF, 0xCA, 0x00, 0x00, 0x00]
        )
        return (
            list(r[0]) if r and r[1] == 0x90 else None
        )

    def _get_uid(self) -> str | None:
        b = self._get_uid_bytes()
        return (
            "".join(f"{x:02X}" for x in b) if b else None
        )

    def read_atc(self) -> dict | None:
        atc_page = self._chip.get("atc_page")
        if not atc_page:
            return None
        cmd    = self._ntag_cmd([0x39, atc_page])
        result = self.reader._transmit(cmd)
        if not result or result[1] != 0x90:
            return None
        resp = result[0]
        if (len(resp) >= 6 and resp[0] == 0xD5
                and resp[1] == 0x41):
            cnt   = resp[3:6]
            count = (
                cnt[0] | (cnt[1] << 8) | (cnt[2] << 16)
            )
            return {
                "count"    : count,
                "count_hex": f"{count:06X}",
                "raw"      : list(cnt),
            }
        return None