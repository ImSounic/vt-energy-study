# Analysis container: regenerates every table and figure of the A3 report from the
# committed raw data in results/. The measurements themselves need the original
# hardware and host OS (IOReport on macOS, RAPL on Linux); see docs/replication.md.
#
#   docker build -t vt-energy-analysis .
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/reproduced:/out" vt-energy-analysis
FROM python:3.14-slim
WORKDIR /vt-energy
ENV MPLCONFIGDIR=/tmp/matplotlib PYTHONDONTWRITEBYTECODE=1
COPY analysis/requirements.txt analysis/requirements.txt
RUN pip install --no-cache-dir -r analysis/requirements.txt
COPY analysis analysis
COPY results results
COPY reproduce.sh .
# ancillary.py also writes its summary next to the data it reads.
RUN chmod -R a+rwX results
ENTRYPOINT ["bash", "reproduce.sh"]
CMD ["/out"]
