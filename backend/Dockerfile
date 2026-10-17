# 改 Python 版本只需：.env 里 PYTHON_VERSION=3.14 然后 docker compose build
# 国内拉不动 docker.io 时：.env 里 PYTHON_IMAGE=docker.m.daocloud.io/library/python
ARG PYTHON_IMAGE=python
ARG PYTHON_VERSION=3.12
FROM ${PYTHON_IMAGE}:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /srv

COPY backend/requirements.txt /srv/requirements.txt
# 国内网络优先清华 PyPI 源，失败回退官方源
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r /srv/requirements.txt \
    || pip install --no-cache-dir -r /srv/requirements.txt

COPY backend/app /srv/app
COPY runner /srv/runner

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
