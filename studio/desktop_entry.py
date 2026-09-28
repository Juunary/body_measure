"""PyInstaller entry point kept outside the package for reliable freezing."""
import sys

from studio.desktop.app import main


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if "--smoke-test" in sys.argv or "--ui-smoke-test" in sys.argv:
        from studio.desktop.smoke import run
        flag = "--ui-smoke-test" if "--ui-smoke-test" in sys.argv else "--smoke-test"
        index = sys.argv.index(flag)
        run(sys.argv[index+1] if len(sys.argv)>index+1 else None, ui=flag=="--ui-smoke-test")
    else:
        main()
