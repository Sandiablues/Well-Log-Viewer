# MultiViewer Well Log Viewer — wells package
# WL-BUILD-001 scaffold
#
# Architecture note:
# All well-domain logic is owned by backend services in this package.
# MSI remains the authority for dataset/source/artifact/representation lifecycle.
# Frontend must fetch and render backend-owned viewer packages only.
