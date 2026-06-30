"""
lo_recalc.py  --  Recalc engine, run by LibreOffice's BUNDLED python (which has
the `uno` module). Connects to a headless soffice instance over a socket,
then for every .xlsx in the given folder: opens it, calls calculateAll(),
and saves it back with cached values populated. After this runs, ordinary
openpyxl(data_only=True) sees the real computed results.

Usage (invoked by simulate_buyer.py, not by hand):
    "<LibreOffice>/program/python.exe" lo_recalc.py <folder> <port>
"""
import glob
import os
import sys
import time

import uno
from com.sun.star.beans import PropertyValue


def connect(port, retries=30):
    localContext = uno.getComponentContext()
    resolver = localContext.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", localContext)
    url = f"uno:socket,host=localhost,port={port};urp;StarOffice.ComponentContext"
    last = None
    for _ in range(retries):
        try:
            ctx = resolver.resolve(url)
            smgr = ctx.ServiceManager
            desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
            return desktop
        except Exception as e:
            last = e
            time.sleep(1)
    raise RuntimeError(f"could not connect to soffice on port {port}: {last}")


def to_url(path):
    return uno.systemPathToFileUrl(os.path.abspath(path))


def main():
    folder, port = sys.argv[1], int(sys.argv[2])
    desktop = connect(port)
    files = sorted(glob.glob(os.path.join(folder, "*.xlsx")))
    hidden = PropertyValue(); hidden.Name = "Hidden"; hidden.Value = True
    saveas = PropertyValue(); saveas.Name = "FilterName"; saveas.Value = "Calc MS Excel 2007 XML"
    done = 0
    for f in files:
        try:
            doc = desktop.loadComponentFromURL(to_url(f), "_blank", 0, (hidden,))
            doc.calculateAll()
            doc.storeToURL(to_url(f), (saveas,))
            doc.close(False)
            done += 1
        except Exception as e:
            sys.stderr.write(f"[recalc-fail] {os.path.basename(f)}: {e}\n")
    print(f"[lo_recalc] recalculated {done}/{len(files)} files")


if __name__ == "__main__":
    main()
