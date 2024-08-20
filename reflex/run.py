from multiprocessing import freeze_support
from dotenv import load_dotenv
from reflex import constants
from reflex.reflex import run


if __name__ == "__main__":
    load_dotenv()
    freeze_support()
    run(
        env=constants.Env.DEV,
        loglevel=constants.LogLevel.INFO,
        frontend_port=str(constants.DefaultPorts.FRONTEND_PORT),
        backend_port=str(constants.DefaultPorts.BACKEND_PORT),
        backend_host="0.0.0.0",
    )
