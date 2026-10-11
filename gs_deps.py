"""Make sure Game Studio's basic Python packages are installed before a tool imports them.

They live in the container's home folder, which a container replacement wipes; this puts
them back on first use (a few seconds) instead of every tool failing. Heavier packages
(torch, diffusers, rembg...) are still installed by the steps that need them.
"""
import importlib.util
import subprocess
import sys

BASE = (('numpy', 'numpy'), ('PIL', 'pillow'), ('trimesh', 'trimesh'), ('scipy', 'scipy'),
        ('fontTools', 'fonttools'), ('brotli', 'brotli'),  # games' build.py subsets their fonts
        ('soundfile', 'soundfile'))  # sound_library.py: reads OGG/WAV/FLAC/MP3, writes MP3
missing = [pkg for mod, pkg in BASE if importlib.util.find_spec(mod) is None]
if missing:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--user', '--no-warn-script-location',
                    '--disable-pip-version-check', *missing], check=True)
    # On a fresh home folder the user package folder did not exist when Python started,
    # so it is not on the path yet: add it before anything imports these.
    import site
    site.addsitedir(site.getusersitepackages())
    importlib.invalidate_caches()
