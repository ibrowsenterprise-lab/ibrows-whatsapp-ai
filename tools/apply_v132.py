#!/usr/bin/env python3
"""Build the verified V132 source from exact V131 Git blob; fail closed on drift."""
import base64
from pathlib import Path
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parent.parent
OLD_SHA = "625a24ab770300271351e25e25b5ee72a71b909c"
NEW_SHA = "9987b17d2e5fc8b3aff74376ffaa8041d5100168"
PATCH_ZLIB_B64 = "eNqtVttu20YQfc9XbJggpCAtRUlOHEsQ4puKGnAdw3bSBoYjrJYjcesVl91dylbrAP2IfmG/pLNLSpbhQO1DX2xeZs6ZPTNzKEopYW1WFHGxfNFsNslkdbO/T2hnt0ua7s/+/gt6cnjx8efL8eGnk9Pj8efRxeXJxzMyJEE36b6jnYQm7+mMSQl6SQsNCwF3hi46vU7wovkfUrkUkFvMFAvGl3SuJkKCy+8GVSndvWSvlWA53b1O0ur6mpqEtNvkMwb1yU9VxlQjTiqXhPHbXN1JSGcwR2RiM2ZJXSCBVFhDcoCUGLYQ+SyusY4V4HNlicgtaA6FJUoTnrF8BmSq9JyYcjIXxgiVt0jBlh6bq9xqJY2LTUGCBeMBp2XOLUYimrFIfa60nSop1CVbwI9IYaIG+cNFEpIqXjqw+LcSK7xEFG6VPpAyCh3vtUi/DoNiBUCxbKDBTdiI8e2I8Sxak0Uufo1LiJhWj+KUWWbAxqZmP1RlnpLhcEjCTtggGmyp88EqbVuKS1gHLphGtR21wTc+7ckZojCuX4eNwWZRL+vHz6gdYoZsCLeWhWtgFkbSdzMKTcHyDTgXHWOhB9ZqMSktRCE2BMIWCVF5W5rtsUwLRqVY+IQCBbbwLMEuJcTcmCu4d4WFqTCFZMt+rnIYcCWV7r+avN3ZTd4PpjgP1Ijfod/ZKe6r2zsQs8z2d5NkwKSY5dSAnPY5uDkbSJEDzaqITrwzCJ9yW6Q8QhDwkoSfcteOtJ7iv//8i1hWEDdTBOfFDaG/vsqEIScW5vEjXK14jEuOa3KUCZlGjuLxsOsxmjN9WzNFsEDqjZGq+uefkjdviL+ILdMz8PcvNx/Ec2Z5BiYKRV6UtmX8WLTcmRj2NGw8a/8TxWuZ3blF7nR6PMy3J6PK0nTkaE+FQaFA13zY0Y2TNAb/klOt+veTvlUX31aG1NmpDam3W7sR2bbpgyqvl+xWRtbrJL1W5zH1Ve1k5+VECk44KxhamrBL8uni1JCoskiCu2Vcg3ImNJgW3iuccNfVFrIvlOD4dIXIcFsLrX5FxUm1CA0E1miBZT5DIMMmEohVt4DLi7tAsCXe/4qqCIkAaI/odLPa0xzqua5ab4BpniFrCvcuyrF545zjaDK9bE+0ujOgkVppRPCD4pQn58c/GBe+QjQlx7LNtJSkmyQ4EKbAAyElOrKvB+bCVnXSCbI6Ns5w9QRn0utTF+c/IBbGlVjjgtkMR2eilIwex0tDNZSRDr62ow/9tYQPtVa01qp9/bV908SI9sPrRtDCRK9+7GAbj3h4oCeQKxScXa4WaIUVjqPCOSva1wndu2k+cDUv3Mei0f7w+vvg9T9ctu+cq795oEqvOAOWgjbXwRF+EoAeVR+m4MZ9bWuIFupJXUOqK+4C3bjfU+zQMMHL0liKHUabQvuHYBvNObZ1zir8FdjWhNF94ca2yki2hv5CL9REWUOv2GzF4EfN1Y3LJdWdu3IjiM69BSouVBEFpyK/RZXP0K5rWUGisJuqo+Uwbc2dsFkUtFk6F3nQ6P+vNa48YG+n9oDe27UBeIPGFfL797zfPrX39l2y61LxYmfPp2IofhGDo9OT0dkVOb84+Xxw9MV7CbkYHRx/6W9YybjU0gxXNa4GgVQ/t8b1z6Oxs18zVDnKNZWlyYZXukTR/gHHXzkJ"

def source_sha():
    return subprocess.check_output(["git", "hash-object", "app.py"], cwd=ROOT, text=True).strip()

def main():
    current = source_sha()
    if current == NEW_SHA:
        print("V132 source already installed and verified")
        return
    if current != OLD_SHA:
        raise SystemExit("Unexpected V131 source SHA: " + current)
    patch = zlib.decompress(base64.b64decode(PATCH_ZLIB_B64)).decode("utf-8")
    subprocess.run(["git", "apply", "--check", "--unidiff-zero"], cwd=ROOT, input=patch, text=True, check=True)
    subprocess.run(["git", "apply", "--unidiff-zero"], cwd=ROOT, input=patch, text=True, check=True)
    if source_sha() != NEW_SHA:
        raise SystemExit("V132 hash mismatch; refusing to commit")
    subprocess.run([sys.executable, "-m", "py_compile", "app.py"], cwd=ROOT, check=True)
    print("V132 SHA-verified app.py generated successfully")

if __name__ == "__main__":
    main()
