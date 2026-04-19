# core/ndef_builder.py

"""
NDEF Builder — NFC card pe likhne ke liye payload banao.

NDEF Structure:
  [TLV: 0x03] [Length] [NDEF Record] [Terminator: 0xFE]

NDEF Record:
  [Header] [Type Length] [Payload Length] [Type] [Payload]

Supported:
  URL  → browser open hoga
  Text → notification mein text dikhega
  Raw  → hex bytes direct

Card Types:
  NTAG213  → 4 bytes/page, page 4 se start
  NTAG215  → 4 bytes/page, page 4 se start
  NTAG216  → 4 bytes/page, page 4 se start
  MIFARE_1K → 16 bytes/block, block 5 se start
  MIFARE_4K → 16 bytes/block, block 5 se start
"""

import struct
from loguru import logger


# ── Card Memory Map ───────────────────────────────────────

CARD_MEMORY = {
    # NTAG family
    "NTAG213" : {
        "family"    : "NTAG",
        "user_bytes": 144,
        "page_size" : 4,
        "start_page": 4,
        "end_page"  : 38,
    },
    "NTAG215" : {
        "family"    : "NTAG",
        "user_bytes": 504,
        "page_size" : 4,
        "start_page": 4,
        "end_page"  : 129,
    },
    "NTAG216" : {
        "family"    : "NTAG",
        "user_bytes": 888,
        "page_size" : 4,
        "start_page": 4,
        "end_page"  : 225,
    },
    # MIFARE family
    "MIFARE_1K": {
        "family"     : "MIFARE",
        "user_bytes" : 752,      # 47 usable blocks × 16
        "block_size" : 16,
        "start_block": 5,        # block 4 = CC, 5 = NDEF start
        "end_block"  : 62,
        # Trailer blocks skip karo (every 4th: 7,11,15...)
        "skip_blocks": set(
            b for b in range(5, 63)
            if (b + 1) % 4 == 0
        ),
    },
    "MIFARE_4K": {
        "family"     : "MIFARE",
        "user_bytes" : 3440,
        "block_size" : 16,
        "start_block": 5,
        "end_block"  : 254,
        "skip_blocks": set(
            b for b in range(5, 255)
            if (b + 1) % 4 == 0
        ),
    },
}

# ── URI Prefix Codes ──────────────────────────────────────

URI_PREFIXES = [
    (0x04, "https://"),
    (0x03, "http://"),
    (0x02, "https://www."),
    (0x01, "http://www."),
    (0x05, "tel:"),
    (0x06, "mailto:"),
    (0x07, "ftp://anonymous:anonymous@"),
    (0x08, "ftp://ftp."),
    (0x09, "ftps://"),
    (0x0A, "sftp://"),
    (0x0D, "ftp://"),
    (0x1D, "file://"),
]

URI_PREFIX_DECODE = {
    code: prefix for code, prefix in URI_PREFIXES
}


class NDEFBuilder:
    """
    NDEF payload builder.

    Usage:
      builder = NDEFBuilder()

      # Build
      payload = builder.build("https://google.com", "url")
      payload = builder.build("Hello World", "text")

      # NTAG ke liye pages
      pages = builder.to_pages_ntag(payload)

      # MIFARE ke liye blocks
      blocks = builder.to_blocks_mifare(payload)

      # Decode
      result = builder.decode(raw_bytes, "MIFARE_1K")
    """

    # ── PUBLIC API ────────────────────────────────────────

    def build(self, data: str,
              data_type: str = "auto") -> bytes:
        """
        Data se NDEF TLV payload banao.

        Args:
          data      : URL string ya text string ya hex string
          data_type : "url" | "text" | "raw" | "auto"

        Returns:
          bytes — card pe likhne ke liye ready

        Auto mode:
          http/https/tel/mailto → url
          baaki sab → text
        """
        if data_type == "auto":
            data_type = self._detect_type(data)

        logger.info(
            f"Building NDEF: type={data_type} "
            f"data={data[:50]}"
        )

        if data_type == "url":
            record = self._build_url_record(data)
        elif data_type == "text":
            record = self._build_text_record(data)
        elif data_type == "raw":
            # Raw hex → directly return without TLV wrap
            # Caller ke paas already complete payload hai
            raw = self._parse_hex(data)
            logger.info(
                f"Raw payload: {len(raw)} bytes"
            )
            return raw
        else:
            raise ValueError(
                f"Unknown data_type: {data_type!r}. "
                f"Use 'url', 'text', 'raw', or 'auto'"
            )

        payload = self._tlv_wrap(record)
        logger.info(
            f"NDEF payload: {len(payload)} bytes "
            f"— {payload.hex().upper()}"
        )
        return payload

    def fits_on_card(self, payload: bytes,
                     card_type: str) -> bool:
        """
        Card pe data fit hoga ya nahi check karo.

        Args:
          payload   : NDEF bytes (from build())
          card_type : "NTAG213" | "NTAG215" | "NTAG216"
                      | "MIFARE_1K" | "MIFARE_4K"

        Returns:
          True agar fit hoga, False agar nahi
        """
        card = CARD_MEMORY.get(card_type)
        if not card:
            logger.warning(
                f"Unknown card type: {card_type} "
                f"— assuming 144 bytes"
            )
            max_bytes = 144
        else:
            max_bytes = card["user_bytes"]

        fits = len(payload) <= max_bytes
        if not fits:
            logger.error(
                f"Data too large: {len(payload)}B "
                f"> {card_type} capacity {max_bytes}B"
            )
        else:
            logger.debug(
                f"Size OK: {len(payload)}B "
                f"/ {max_bytes}B ({card_type})"
            )
        return fits

    # ── NTAG METHODS ──────────────────────────────────────

    def to_pages_ntag(self, payload: bytes,
                      start_page: int = 4) -> list:
        """
        NDEF payload → NTAG pages list.

        NTAG page = 4 bytes.
        Page 4 = user memory start.
        Last page padded with 0x00.

        Returns:
          [(page_num, [b0,b1,b2,b3]), ...]
        """
        # Pad to 4-byte boundary
        remainder = len(payload) % 4
        if remainder != 0:
            pad    = 4 - remainder
            padded = payload + bytes(pad)
        else:
            padded = payload

        pages = []
        for i in range(0, len(padded), 4):
            chunk    = list(padded[i:i + 4])
            page_num = start_page + (i // 4)
            pages.append((page_num, chunk))

        logger.debug(
            f"NTAG pages: {len(pages)} "
            f"(page {start_page} to "
            f"{start_page + len(pages) - 1})"
        )
        return pages

    # Legacy alias
    def to_pages(self, payload: bytes,
                 start_page: int = 4) -> list:
        return self.to_pages_ntag(payload, start_page)

    # ── MIFARE METHODS ────────────────────────────────────

    def to_blocks_mifare(self, payload: bytes,
                         card_type: str = "MIFARE_1K"
                         ) -> list:
        """
        NDEF payload → MIFARE blocks list.

        MIFARE block = 16 bytes.
        Trailer blocks automatically skip hote hain.

        Returns:
          [(block_num, [16 bytes]), ...]
          Trailer blocks NOT included (caller skip karega)
        """
        card = CARD_MEMORY.get(card_type, CARD_MEMORY["MIFARE_1K"])

        # Pad to 16-byte boundary
        remainder = len(payload) % 16
        if remainder != 0:
            pad    = 16 - remainder
            padded = payload + bytes(pad)
        else:
            padded = payload

        chunks = [
            list(padded[i:i + 16])
            for i in range(0, len(padded), 16)
        ]

        logger.debug(
            f"MIFARE blocks needed: {len(chunks)} "
            f"({len(payload)}B → padded {len(padded)}B)"
        )
        return chunks

    def get_writable_blocks_mifare(
        self, card_type: str = "MIFARE_1K"
    ) -> list:
        """
        MIFARE ke liye writable block numbers list.
        Trailer blocks aur reserved blocks skip.

        Returns:
          [5, 6, 8, 9, 10, 12, 13, 14, ...]
          (Block 4=CC, trailers 7,11,15... skip)
        """
        card = CARD_MEMORY.get(
            card_type, CARD_MEMORY["MIFARE_1K"]
        )
        start     = card.get("start_block", 5)
        end       = card.get("end_block", 62)
        skip_set  = card.get("skip_blocks", set())
        reserved  = {0, 1, 2, 3, 4}  # MAD + CC blocks

        blocks = [
            b for b in range(start, end + 1)
            if b not in skip_set
            and b not in reserved
        ]
        return blocks

    # ── DECODE ────────────────────────────────────────────

    def decode(self, raw_bytes: bytes,
               card_type: str = "NTAG213") -> dict:
        """
        Card se read kiye raw bytes → human readable dict.

        Args:
          raw_bytes : card se padhe bytes
          card_type : card type (MIFARE ke liye trailer
                      blocks filter karta hai)

        Returns:
          {
            "type": "url" | "text" | "unknown",
            "data": "https://..." | "Hello..." | hex,
            "raw_hex": "03 0F D1...",
            "card_type": "NTAG213",
          }
        """
        # MIFARE ke liye trailer bytes remove karo
        family = CARD_MEMORY.get(
            card_type, {}
        ).get("family", "NTAG")

        if family == "MIFARE":
            raw_bytes = self._filter_mifare_trailers(
                raw_bytes, card_type
            )

        result = self._parse_tlv(raw_bytes)
        result["card_type"] = card_type
        result["raw_hex"]   = raw_bytes.hex().upper()
        return result

    # Legacy alias
    def decode_from_card(self, raw_bytes: bytes) -> dict:
        return self.decode(raw_bytes)

    def _filter_mifare_trailers(
        self, raw_bytes: bytes, card_type: str
    ) -> bytes:
        """
        MIFARE raw bytes se trailer block bytes remove karo.

        MIFARE memory structure:
          Block 5  → data [16 bytes]
          Block 6  → data [16 bytes]
          Block 7  → TRAILER [16 bytes] ← skip
          Block 8  → data [16 bytes]
          Block 9  → data [16 bytes]
          Block 10 → data [16 bytes]
          Block 11 → TRAILER [16 bytes] ← skip
          ...

        raw_bytes assume: block 5 se start, continuous 16B chunks
        """
        card      = CARD_MEMORY.get(
            card_type, CARD_MEMORY["MIFARE_1K"]
        )
        start     = card.get("start_block", 5)
        skip_set  = card.get("skip_blocks", set())

        filtered = bytearray()
        block    = start

        for i in range(0, len(raw_bytes), 16):
            chunk = raw_bytes[i:i + 16]
            if len(chunk) < 16:
                filtered.extend(chunk)
                break

            if block not in skip_set:
                filtered.extend(chunk)
            else:
                logger.debug(
                    f"Filtered trailer block {block}"
                )

            block += 1

            # Stop at terminator
            if 0xFE in chunk:
                break

        return bytes(filtered)

    # ── RECORD BUILDERS ───────────────────────────────────

    def _build_url_record(self, url: str) -> bytes:
        """
        URI Record (type="U").
        Phone mein browser open hoga.

        Payload:
          [prefix_code: 1B] [url_remainder: NB]
        """
        prefix_code  = 0x00
        encoded_url  = url

        for code, prefix in URI_PREFIXES:
            if url.lower().startswith(prefix.lower()):
                prefix_code = code
                encoded_url = url[len(prefix):]
                break

        url_bytes = encoded_url.encode("utf-8")
        payload   = bytes([prefix_code]) + url_bytes

        logger.debug(
            f"URL record: prefix=0x{prefix_code:02X} "
            f"remainder={encoded_url[:40]}"
        )

        return self._build_record(
            tnf=0x01,
            type_bytes=b"U",
            payload=payload,
        )

    def _build_text_record(self, text: str,
                            lang: str = "en") -> bytes:
        """
        Text Record (type="T").
        Phone mein text dikhega.

        Payload:
          [status: 1B] [lang: NB] [text: NB]
          status bit7=0 → UTF-8 encoding
          status bits5-0 → lang length
        """
        lang_bytes = lang.encode("ascii")
        text_bytes = text.encode("utf-8")

        # Status byte: UTF-8 (bit7=0) + lang length
        status  = len(lang_bytes) & 0x3F
        payload = bytes([status]) + lang_bytes + text_bytes

        logger.debug(
            f"Text record: lang={lang} "
            f"text={text[:40]}"
        )

        return self._build_record(
            tnf=0x01,
            type_bytes=b"T",
            payload=payload,
        )

    def _build_record(self, tnf: int,
                      type_bytes: bytes,
                      payload: bytes,
                      is_first: bool = True,
                      is_last: bool = True) -> bytes:
        """
        Low-level NDEF record assembler.

        Header byte:
          bit7 MB = Message Begin (first record)
          bit6 ME = Message End   (last record)
          bit5 CF = Chunk Flag    (0 = not chunked)
          bit4 SR = Short Record  (payload < 256B)
          bit3 IL = ID Length     (0 = no ID field)
          bits2-0 TNF = Type Name Format
        """
        header = tnf & 0x07  # TNF in lower 3 bits

        if is_first:
            header |= 0x80  # MB
        if is_last:
            header |= 0x40  # ME

        is_short = len(payload) < 256
        if is_short:
            header       |= 0x10  # SR
            payload_len   = bytes([len(payload)])
        else:
            payload_len   = struct.pack(">I", len(payload))

        return (
            bytes([header])
            + bytes([len(type_bytes)])
            + payload_len
            + type_bytes
            + payload
        )

    # ── TLV ──────────────────────────────────────────────

    def _tlv_wrap(self, ndef_record: bytes) -> bytes:
        """
        NDEF record → TLV format.

        TLV format:
          0x03         = NDEF Message tag
          [length]     = 1 byte agar < 255, else 0xFF + 2B
          [ndef_bytes] = record bytes
          0xFE         = Terminator TLV

        Length encoding:
          0-254   : 1 byte
          255+    : 0xFF [high byte] [low byte]
        """
        n = len(ndef_record)

        if n < 255:
            length_bytes = bytes([n])
        else:
            length_bytes = (
                bytes([0xFF]) + struct.pack(">H", n)
            )

        return (
            bytes([0x03])
            + length_bytes
            + ndef_record
            + bytes([0xFE])
        )

    # ── TLV PARSER ────────────────────────────────────────

    def _parse_tlv(self, raw: bytes) -> dict:
        """
        Raw bytes se NDEF TLV parse karo.
        """
        try:
            i = 0
            while i < len(raw):
                tag = raw[i]

                if tag == 0x00:    # NULL TLV
                    i += 1
                    continue
                if tag == 0xFE:    # Terminator
                    break
                if tag != 0x03:    # Not NDEF — skip
                    i += 1
                    continue

                i += 1
                if i >= len(raw):
                    break

                # Length
                length = raw[i]
                if length == 0xFF:
                    i += 1
                    if i + 2 > len(raw):
                        break
                    length = struct.unpack(
                        ">H", raw[i:i + 2]
                    )[0]
                    i += 2
                else:
                    i += 1

                if i + length > len(raw):
                    break

                ndef_bytes = raw[i:i + length]
                return self._parse_record(ndef_bytes)

        except Exception as e:
            logger.error(f"TLV parse error: {e}")

        return {
            "type": "unknown",
            "data": raw.hex().upper(),
        }

    def _parse_record(self, record: bytes) -> dict:
        """
        NDEF record bytes → dict.
        """
        if len(record) < 3:
            return {"type": "unknown", "data": ""}

        header   = record[0]
        type_len = record[1]
        is_short = bool(header & 0x10)

        if is_short:
            pay_len    = record[2]
            type_start = 3
        else:
            if len(record) < 6:
                return {"type": "unknown", "data": ""}
            pay_len    = struct.unpack(
                ">I", record[2:6]
            )[0]
            type_start = 6

        type_bytes = record[
            type_start: type_start + type_len
        ]
        payload = record[
            type_start + type_len:
            type_start + type_len + pay_len
        ]

        rec_type = type_bytes.decode(
            "ascii", errors="ignore"
        )

        # ── URL Record ────────────────────────────────────
        if rec_type == "U" and len(payload) >= 1:
            prefix   = URI_PREFIX_DECODE.get(
                payload[0], ""
            )
            url_body = payload[1:].decode(
                "utf-8", errors="ignore"
            )
            return {
                "type": "url",
                "data": prefix + url_body,
            }

        # ── Text Record ───────────────────────────────────
        if rec_type == "T" and len(payload) >= 1:
            lang_len = payload[0] & 0x3F
            lang     = payload[
                1: 1 + lang_len
            ].decode("ascii", errors="ignore")
            text     = payload[
                1 + lang_len:
            ].decode("utf-8", errors="ignore")
            return {
                "type"    : "text",
                "data"    : text,
                "language": lang,
            }

        # ── Unknown ───────────────────────────────────────
        return {
            "type": rec_type or "unknown",
            "data": payload.hex().upper(),
        }

    # ── HELPERS ───────────────────────────────────────────

    def _detect_type(self, data: str) -> str:
        """Auto detect URL ya text"""
        prefixes = (
            "http://", "https://",
            "tel:", "mailto:",
            "ftp://", "ftps://",
        )
        if any(
            data.lower().startswith(p)
            for p in prefixes
        ):
            return "url"
        return "text"

    def _parse_hex(self, hex_str: str) -> bytes:
        """Hex string → bytes"""
        cleaned = (
            hex_str.replace(" ", "")
                   .replace(":", "")
                   .replace("-", "")
                   .strip()
        )
        return bytes.fromhex(cleaned)

    def max_data_size(self, card_type: str) -> int:
        """Card type ke liye max usable bytes"""
        card = CARD_MEMORY.get(card_type)
        if not card:
            return 144
        return card["user_bytes"]

    def summary(self, payload: bytes,
                card_type: str) -> dict:
        """
        Payload ka summary — write se pehle show karo.
        """
        card      = CARD_MEMORY.get(card_type, {})
        family    = card.get("family", "NTAG")
        max_bytes = card.get("user_bytes", 144)

        if family == "MIFARE":
            blocks_needed = (
                (len(payload) + 15) // 16
            )
            unit_info = {
                "unit"       : "blocks",
                "unit_size"  : 16,
                "count"      : blocks_needed,
            }
        else:
            pages_needed = (
                (len(payload) + 3) // 4
            )
            unit_info = {
                "unit"       : "pages",
                "unit_size"  : 4,
                "count"      : pages_needed,
            }

        return {
            "payload_bytes": len(payload),
            "max_bytes"    : max_bytes,
            "fits"         : len(payload) <= max_bytes,
            "usage_pct"    : round(
                len(payload) / max_bytes * 100, 1
            ),
            "hex_preview"  : payload.hex().upper()[:64],
            **unit_info,
        }