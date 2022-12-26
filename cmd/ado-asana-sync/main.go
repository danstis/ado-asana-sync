package main

import (
	"log"

	"github.com/danstis/ado-asana-sync/internal/version"
)

// Main entry point for the app.
func main() {
	log.Printf("Version %q", version.Version)
}
