FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

RUN dnf install -y \
    cairo \
    pango \
    gdk-pixbuf2 \
    libffi \
    libjpeg-turbo \
    libxml2 \
    libxslt \
    freetype \
    fontconfig \
    harfbuzz \
    glib2 \
    && dnf clean all

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt -t /var/task

COPY . .

CMD ["lambda_handler.handler"]
