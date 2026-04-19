# debug_card.py — ye script run karo card pe rakh ke

def debug_mifare_raw(writer):
    """
    Card ki exact memory state print karo.
    Ye batayega kya actually card pe hai.
    """
    print("\n" + "═"*60)
    print("  MIFARE RAW MEMORY DUMP")
    print("═"*60)
    
    critical_blocks = {
        0: "Manufacturer",
        1: "MAD1",
        2: "MAD2", 
        4: "CC (Capability Container)",
        5: "NDEF Block 1",
        6: "NDEF Block 2",
        8: "NDEF Block 3",
        9: "NDEF Block 4",
        10: "NDEF Block 5",
    }
    
    for block, name in critical_blocks.items():
        data = writer._mifare_read_block(block)
        if data:
            hex_str = bytes(data).hex().upper()
            print(f"\n  Block {block:2d} [{name}]:")
            print(f"    HEX: {' '.join(hex_str[i:i+2] for i in range(0,32,2))}")
            
            # Block specific analysis
            if block == 4:  # CC
                print(f"    Magic  : 0x{data[0]:02X} {'✓' if data[0]==0xE1 else '✗ WRONG!'}")
                print(f"    Version: 0x{data[1]:02X} {'✓' if data[1]==0x10 else '✗ WRONG! Should be 0x10'}")
                print(f"    Size   : 0x{data[2]:02X}")
                print(f"    Access : 0x{data[3]:02X} {'✓ R/W' if data[3]==0x00 else '✗ WRONG!'}")
                
            if block == 5:  # NDEF
                print(f"    TLV Tag: 0x{data[0]:02X} {'✓ NDEF' if data[0]==0x03 else '✗ WRONG! Should be 0x03'}")
                print(f"    Length : 0x{data[1]:02X} ({data[1]} bytes)")
                if data[1] == 0:
                    print(f"    ✗ EMPTY NDEF! Data not written here.")
                    
        else:
            print(f"\n  Block {block:2d} [{name}]: ✗ CANNOT READ")
    
    print("\n" + "═"*60)
    print("  SECTOR KEY MAP:")
    print("═"*60)
    for s in range(8):
        info = writer._sectors.get(s)
        trailer = s * 4 + 3
        if info:
            print(
                f"  Sector {s}: "
                f"key={bytes(info.read_key).hex().upper()} "
                f"kt={'A' if info.read_kt==0x60 else 'B'} "
                f"writable={info.writable} "
                f"write_kt={'A' if info.write_kt==0x60 else 'B'}"
            )
        else:
            print(f"  Sector {s}: ✗ NOT IN MAP")
    print("═"*60)