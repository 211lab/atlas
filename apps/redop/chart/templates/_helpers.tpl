{{/* Common template helpers for the RED Operations Platform chart. */}}

{{- define "redop.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "redop.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "redop.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "redop.labels" -}}
helm.sh/chart: {{ include "redop.chart" . }}
app.kubernetes.io/name: {{ include "redop.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "redop.selectorLabels" -}}
app.kubernetes.io/name: {{ include "redop.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "redop.apiImage" -}}
{{- $tag := .Values.apiTag | default .Chart.AppVersion -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.api.repository $tag -}}
{{- end -}}

{{- define "redop.cockpitImage" -}}
{{- $tag := .Values.cockpitTag | default .Chart.AppVersion -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.cockpit.repository $tag -}}
{{- end -}}

{{- define "redop.workerImage" -}}
{{- $tag := .Values.apiTag | default .Chart.AppVersion -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.worker.repository $tag -}}
{{- end -}}

{{- define "redop.migrationJobName" -}}
{{- printf "%s-migrate" (include "redop.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
