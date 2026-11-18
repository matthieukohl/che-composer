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
| `wmo-raf/addon/` | CHE add-on for an existing WMO-RAF CAP Composer installation | In preparation |
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

CHE Composer can be added to an existing **WMO-RAF CAP Composer 1.3.6** installation. It adds CHE features to CAP Composer without replacing it.

### Install CHE in a test environment

**1. Download CHE Composer.** Open Terminal and run:

```bash
git clone https://github.com/matthieukohl/che-composer.git
cd che-composer
```

**2. Check the existing CAP Composer folder.** Run:

```bash
./wmo-raf/addon/install.sh plan --cap-path /path/to/cap-composer
```

Replace `/path/to/cap-composer` with the full path to your CAP Composer folder. For example, if the folder is at `/home/meteorology/cap-composer`, use that path instead.

The check confirms that the expected CAP Composer files are present, that the CHE files are complete, and that the changes should not conflict with existing files. **This check does not change CAP Composer.**

**3. Install CHE in an approved test environment only.** Run:

```bash
./wmo-raf/addon/install.sh install --cap-path /path/to/cap-composer
```

Replace the example path as in Step 2. The installer adds 36 CHE files, two branding files and makes three changes to CAP Composer: **41 file operations in total**.

**4. Restart and check.** Rebuild and restart the existing CAP Composer application using its own Docker Compose setup. Then confirm that CHE appears in the admin interface and that existing CAP alerts are still there. Docker commands vary between installations.

### Does the installer save the original files?

**Yes. Before changing CAP Composer, it saves copies of the three original CAP configuration files it needs to modify.** It also records which files it adds and changes, so its recovery tool can reverse those source-file changes when safe to do so.

This is **not a complete backup**. The installer does not automatically back up the CAP database, existing alerts, uploaded images or other data. Keep separate backups of those items.

### What have we tested?

We successfully added CHE to a fresh CAP Composer 1.3.6 test installation. We checked all 41 file changes, started CAP Composer with CHE, confirmed that the CHE database update was applied, and verified that an existing CAP alert remained exactly unchanged.

### Important: test use only

**The current installer only allows installation in approved disposable test environments.** It will refuse an operational national CAP Composer installation. Backup and recovery procedures and other safety checks need further testing before use on an operational system.

A separate `deployment.json` option is provided for more detailed deployment safety checks. **It is not needed for the simple test installation shown above**, and does not remove the current restriction on operational installations.

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
