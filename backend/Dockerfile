FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

# Minimal native deps:
# - graphviz: provides `dot` for Graphviz rendering
# - fontconfig + freetype: font discovery/rasterization
# - cairo: reliable SVG/PNG rendering path (safe baseline)
RUN dnf install -y \
    graphviz \
    fontconfig \
    freetype \
    cairo \
    && dnf clean all

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt -t /var/task

COPY . .

CMD ["lambda_handler.handler"]
