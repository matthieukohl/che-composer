# WMO Catalogue of Hazardous Events (CHE) Composer

CHE Composer is an open-source prototype web application designed to support National Meteorological and Hydrological Services (NMHSs) in recording, managing, visualizing and linking hazardous events.

The application supports national implementation of the WMO Cataloguing of Hazardous Events (WMO-CHE) methodology, as described in:

[Guidance for Implementation of the WMO Cataloguing of Hazardous Weather, Climate, Water and Related Environmental Events (WMO-No. 1377)](https://wmo.int/events/workshop/delta-training-undrr).

CHE Composer is built on [WMO-RAF CAP Composer](https://github.com/wmo-raf/cap-composer), reusing its existing Django, Wagtail, PostgreSQL and Docker infrastructure.

CAP Composer and CHE Composer serve complementary but distinct purposes:

- CAP Composer supports the creation, management and dissemination of Common Alerting Protocol (CAP) warnings.
- CHE Composer supports the systematic documentation and cataloguing of hazardous events.

CHE records are maintained separately from CAP alerts. The extension does not change the CAP alert data model or its publication and dissemination workflows.

## Project Status

CHE Composer is currently a functional prototype undergoing packaging and installation testing.

The combined CAP + CHE installation based on WMO-RAF CAP Composer has been successfully tested in an isolated Docker environment, including:

- Building the application and background-worker images.
- Initializing a fresh PostgreSQL/PostGIS database.
- Applying the CHE database migration.
- Creating administrator accounts.
- Accessing the administration interface.
- Displaying the authenticated CHE Global Map.

The original development prototype has also been used to test CHE catalogue functions, event relationships and transfers to a local UNDRR DELTA Resilience installation.

## Features

### Hazardous-Event Catalogue

CHE Composer provides a dedicated interface for creating, reviewing, editing, searching and filtering hazardous-event records.

The data model supports:

- A permanent event UUID and originating institution.
- Event start and end dates.
- Classification using the 30 WMO event types.
- National hazard specification and event description.
- Geographic event footprints represented using GeoJSON.
- Event status: ongoing, completed or validated.
- Linkage to related or higher-order hazardous events through their UUIDs.
- Optional indicative impact information and affected sectors.
- Record creation and update metadata.

The catalogue includes basic data-consistency checks and uses the existing Wagtail administration and permission-management framework.

### Geographic Visualization

The CHE Global Map displays event locations and geographic footprints, with filters and access to individual event information.

A CHE-specific spatial editing interface allows geographic event areas to be defined and stored as GeoJSON-compatible data.

The map displays records available within the CHE Composer installation. It is not an operational global WMO hazardous-event aggregation service.

### Event Relationships and Hierarchy

The CHE Network Viewer supports exploring explicitly recorded relationships between hazardous events.

Users can search and filter records and visualize parent–child linkages using network and hierarchy layouts.

The application does not automatically infer or scientifically validate causal relationships between events.

### Integration with UNDRR DELTA Resilience

CHE Composer includes functionality for transferring selected hazardous-event records to [UNDRR DELTA Resilience](https://www.undrr.org/building-risk-knowledge/disaster-losses-and-damages-tracking-system-delta-resilience).

The developed integration includes:

- Connection to an authorized DELTA installation using its website address and API key.
- Mapping between the 30 WMO-CHE event types and proposed Hazard Information Profile (HIP) classifications.
- Retrieval of installation-specific DELTA hazard identifiers.
- Conversion of CHE event information into DELTA-compatible records.
- Preservation of the original CHE UUID and geographic polygon coordinates.
- Creation or updating of matching DELTA records.
- Selection and batch transfer of eligible events, with individual transfer results.

The original prototype has successfully transferred individual and batch events to a locally installed DELTA instance.

## Repository Structure

The repository is organized to support two installation approaches for each CAP Composer foundation: a complete combined installation and a CHE add-on for an existing installation.

| Directory | Purpose | Status |
|---|---|---|
| `wmo-raf/combined/` | Complete WMO-RAF CAP Composer + CHE installation | Initial installation tested |
| `wmo-raf/addon/` | CHE add-on for an existing WMO-RAF CAP Composer installation | Initial installation tested (test environments only) |
| `wmo/combined/` | Combined installation based on the alternative WMO CAP Composer repository | Planned |
| `wmo/addon/` | CHE add-on for the alternative WMO installation | Planned |
| `che-core/` | Shared CHE application source | Included |
| `docs/` | Additional project documentation | In preparation |

The `che-core/` directory currently contains shared source files and is not a separately installable Python package.

## Installation — WMO-RAF Combined Edition

This installation provides CAP Composer and CHE Composer together, including the required application and database infrastructure.

Prerequisites:

- Docker Desktop or Docker Engine.
- Docker Compose.
- Sufficient local storage for the application images and PostgreSQL database.

### 1. Clone the repository

```bash
git clone https://github.com/matthieukohl/che-composer.git
cd che-composer/wmo-raf/combined
```

### 2. Create local configuration files

```bash
cp .env.standalone.sample .env
cp nginx/nginx.conf.sample nginx/nginx.conf
cp docker-compose.sample.yml docker-compose.yml
```

### 3. Configure environment variables

Edit `.env` and set the required variables:

- `SECRET_KEY`
- `DB_PASSWORD`
- `REDIS_PASSWORD`
- `UID`
- `GID`

Use unique secrets and the appropriate user and group identifiers for your host environment.

Do not commit `.env` or share its credentials.

Review additional configuration variables in the [WMO-RAF combined installation documentation](wmo-raf/combined/README.md).

### 4. Create persistent storage directories

```bash
mkdir -p docker/volumes/db docker/volumes/backup docker/volumes/static docker/volumes/media
```

Ensure the configured Docker user has appropriate write permissions.

### 5. Build and start the application

```bash
docker compose build
docker compose up -d
```

### 6. Check the installation

```bash
docker compose ps
docker compose logs --tail=100
```

### 7. Create an administrator account

```bash
docker compose exec capcomposer capcomposer createsuperuser
```

### 8. Open CHE Composer

With the default local port and administration path:

- CAP Composer administration: http://localhost/cap-admin/
- CHE Events catalogue: http://localhost/cap-admin/che_events/

Sign in using an authorized account.

The CHE Events catalogue is the primary entry point for creating and managing hazardous-event records. The Global Map, Network Viewer and Push to DELTA functions are accessible through the application's navigation interface.

### Installing alongside an existing CAP Composer instance

For independent installations, configure separate database storage, Docker resources, credentials and exposed ports.

Do not reuse the database volumes or runtime configuration of an existing operational installation.

## CHE Add-On Installation

CHE Composer can be added to WMO-RAF CAP Composer version 1.3.6. It adds the CHE tools to the existing application without replacing CAP Composer or its alerts.

### 1. Download CHE Composer

Open Terminal and run:

```bash
git clone https://github.com/matthieukohl/che-composer.git
cd che-composer
```

### 2. Check your CAP Composer installation

Run:

```bash
./wmo-raf/addon/install.sh plan --cap-path /path/to/cap-composer
```

Replace `/path/to/cap-composer` with the full location of your existing CAP Composer folder. For example, if it is in `/home/meteorology/cap-composer`, run:

```bash
./wmo-raf/addon/install.sh plan --cap-path /home/meteorology/cap-composer
```

This check does not change any files. It checks that the expected CAP Composer files are present, all CHE files are ready, and there are no conflicting files or unsafe locations.

### 3. Install CHE in a test installation

For an allowed test installation, run:

```bash
./wmo-raf/addon/install.sh install --cap-path /path/to/cap-composer
```

Replace the example folder path as in Step 2.

The installer makes 41 file changes:

- Adds 36 files containing the CHE features.
- Adds two files to display the CAP + CHE Composer logo instead of the original CAP-only logo.
- Updates three existing CAP Composer files:
  - `config/settings/base.py` — tells CAP Composer to load CHE.
  - `config/urls.py` — connects the CHE pages to the application.
  - `config/templates/wagtailadmin/base.html` — adds the CHE branding to the administration interface.

Before making those changes, the installer saves copies of the three original CAP files and records which files it adds. Its recovery tool can use this information to undo the CHE file changes, provided the files have not been changed again in a way that makes recovery unsafe.

### 4. Rebuild and restart CAP Composer

After adding CHE, CAP Composer must load the new files. If your existing installation uses a standard Docker Compose setup, open a Terminal in the CAP Composer folder and run:

```bash
cd /path/to/cap-composer
docker compose build
docker compose up -d
```

Replace `/path/to/cap-composer` with your own CAP Composer folder. For example:

```bash
cd /home/meteorology/cap-composer
docker compose build
docker compose up -d
```

These are example commands. They work when Docker Compose is already set up in that folder. If your installation uses different Compose files or service names, use the same Docker setup you normally use to restart CAP Composer. Do not create a second database or replace your existing database.

Then open your usual CAP Composer administration page. Check that CHE appears and that your existing CAP alerts are still present. Confirm that the CHE database update has been applied.

### Does the installer make a backup?

It saves copies of the three original CAP configuration files that it changes. This lets the recovery tool reverse the CHE source-file changes when it is safe to do so.

It does not make a full system backup. In particular, it does not automatically back up CAP alerts in the database, uploaded images, or other stored data. Those need separate backups.

### What have we tested?

We tested the add-on with a fresh CAP Composer 1.3.6 installation. All 41 file changes were verified. We rebuilt and started the application, confirmed CHE was loaded and its database update was applied, and checked that an existing CAP alert remained exactly unchanged.

### Important: the current release is for testing only

The installer checks the location of the CAP Composer folder before allowing changes. It accepts only specific, temporary test folders used for development and rejects ordinary operational CAP Composer folders. This prevents someone from accidentally running the current development installer on a national warning system.

The folder check is not proof that an installation is safe for real-world use. Full backup and recovery testing is still needed before installation on an operational system can be enabled. Do not rename or move a real national installation simply to bypass this restriction.

### Add-on deployment workflow (development release candidate)

The CHE add-on is designed for existing WMO-RAF CAP Composer v1.3.6
installations. Unlike the combined edition described above, it adds CHE
to an existing CAP Composer deployment through targeted changes intended
to preserve national settings, URL registrations, and existing branding.

The add-on contains 36 CHE source files, two branding assets, and three
targeted configuration patches: 41 source operations in total.

#### Deployment configuration

After cloning this repository, copy
`wmo-raf/addon/deployment.example.json` to your private `deployment.json`
and replace the placeholders with the actual CAP project path, Docker
services, database identities, and recovery evidence paths. Do not commit
private deployment settings, credentials, or recovery evidence to Git.

#### Terminal workflow

```sh
# Preview the 41 source operations; no CAP files are changed
./wmo-raf/addon/install.sh plan --config deployment.json

# Run the national deployment safety checks
./wmo-raf/addon/install.sh preflight --config deployment.json

# Intended install interface — currently restricted to disposable tests
./wmo-raf/addon/install.sh install --config deployment.json

# Source recovery from an existing CHE journal
./wmo-raf/addon/install.sh recover --config deployment.json
```

#### Current development status

This is a development release candidate, not a production-ready add-on.
The installation and recovery engines currently reject operational CAP
project paths. A successful preflight does not override this restriction.
The complete seven-check deployment preflight has not yet been proven
against a real national deployment.

In tested disposable environments, installation journals all 41 operations
before making source changes. Recovery restores the three original CAP
configuration files and their permissions, and removes 38 CHE-created
files if they remain unmodified. Source recovery does not require a fresh
Docker or PostgreSQL preflight.

Recovery covers CHE-managed source files only; it is not a substitute for
independently verified database backups or infrastructure recovery. Keep
the recovery journal after an interrupted installation for review.

#### Remaining requirements for production authorization

1. Independently authenticate and protect recovery-journal evidence.
2. Complete interrupted-installation and recovery tests on the final build.
3. Verify backup and restoration against a realistic Docker/PostgreSQL
   deployment and its actual database/service identities.
4. Review filesystem race conditions, trust boundaries, and permissions.
5. Test country-specific CAP customizations and authorize operational
   paths only after the deployment and recovery safety gates pass.

Do not bypass the test-workspace restriction or use this release on an
operational CAP Composer installation.

## Origins and Attribution

CHE Composer is based on the open-source WMO-RAF CAP Composer project.

Original CAP Composer authors:

- Erick Otenyo
- Grace Amondi

CHE Composer extension development:

- Matthieu Kohl

The combined edition retains the original CAP Composer source code, copyright notices and license.

CHE Composer is an independent extension of the upstream project and does not imply official endorsement by the World Meteorological Organization or WMO-RAF.

## License

The underlying CAP Composer project is distributed under the MIT License.

See [the upstream license included in the combined edition](wmo-raf/combined/LICENSE).

Third-party software and bundled assets may be subject to additional licenses.

## References

- World Meteorological Organization. Guidance for Implementation of the WMO Cataloguing of Hazardous Weather, Climate, Water and Related Environmental Events (WMO-No. 1377).
- [WMO information on WMO-CHE implementation](https://wmo.int/events/workshop/delta-training-undrr)
- [WMO-RAF CAP Composer](https://github.com/wmo-raf/cap-composer)
- [UNDRR DELTA Resilience](https://www.undrr.org/building-risk-knowledge/disaster-losses-and-damages-tracking-system-delta-resilience)

Upstream CAP Composer foundation:

- Version: `1.3.6`
- Git commit: `527751b04903e67dd6419750a157ec32e6940756`
