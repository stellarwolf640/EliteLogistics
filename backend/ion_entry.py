import traceback

from elite_logistics.config import get_settings
from elite_logistics.desktop import main

if __name__ == "__main__":
    try:
        main()
    except BaseException:
        try:
            path = get_settings().paths.logs / "fatal-startup.log"
            path.write_text(traceback.format_exc(), encoding="utf-8")
        finally:
            raise
