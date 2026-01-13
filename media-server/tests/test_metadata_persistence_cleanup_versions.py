from sqlmodel import SQLModel, Session, create_engine, select

from models.media_models import FileAsset, MediaCore, MediaVersion
from services.media.metadata_persistence_service import MetadataPersistenceService


def test_cleanup_orphan_versions_after_rebind_deletes_old_version_without_assets():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        core = MediaCore(id=10, user_id=1, kind="episode", title="E")
        session.add(core)
        session.commit()

        old_version = MediaVersion(user_id=1, core_id=10, tags="old", scope="episode_child")
        new_version = MediaVersion(user_id=1, core_id=10, tags="new", scope="episode_child")
        session.add(old_version)
        session.add(new_version)
        session.commit()

        asset = FileAsset(
            user_id=1,
            storage_id=1,
            full_path="/x/1.mp4",
            filename="1.mp4",
            relative_path="1.mp4",
            size=1,
            version_id=new_version.id,
            core_id=10,
        )
        session.add(asset)
        session.commit()

        svc = MetadataPersistenceService()
        svc._cleanup_orphan_versions_after_rebind(
            session=session,
            user_id=1,
            old_version_id=old_version.id,
            new_version_id=new_version.id,
            old_season_version_id=None,
            new_season_version_id=None,
        )
        session.commit()

        assert session.get(MediaVersion, old_version.id) is None
        assert session.get(MediaVersion, new_version.id) is not None


def test_cleanup_orphan_versions_after_rebind_deletes_old_season_and_children_without_assets():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        season_core = MediaCore(id=100, user_id=1, kind="season", title="S1")
        ep_core = MediaCore(id=101, user_id=1, kind="episode", title="E1")
        session.add(season_core)
        session.add(ep_core)
        session.commit()

        old_season_version = MediaVersion(user_id=1, core_id=100, tags="sv-old", scope="season_group")
        new_season_version = MediaVersion(user_id=1, core_id=100, tags="sv-new", scope="season_group")
        session.add(old_season_version)
        session.add(new_season_version)
        session.commit()

        old_child = MediaVersion(
            user_id=1,
            core_id=101,
            tags="ev-old",
            scope="episode_child",
            parent_version_id=old_season_version.id,
        )
        new_child = MediaVersion(
            user_id=1,
            core_id=101,
            tags="ev-new",
            scope="episode_child",
            parent_version_id=new_season_version.id,
        )
        session.add(old_child)
        session.add(new_child)
        session.commit()

        asset = FileAsset(
            user_id=1,
            storage_id=1,
            full_path="/x/1.mp4",
            filename="1.mp4",
            relative_path="1.mp4",
            size=1,
            core_id=101,
            version_id=new_child.id,
            season_version_id=new_season_version.id,
        )
        session.add(asset)
        session.commit()

        svc = MetadataPersistenceService()
        svc._cleanup_orphan_versions_after_rebind(
            session=session,
            user_id=1,
            old_version_id=None,
            new_version_id=None,
            old_season_version_id=old_season_version.id,
            new_season_version_id=new_season_version.id,
        )
        session.commit()

        remaining = session.exec(
            select(MediaVersion).where(MediaVersion.user_id == 1).order_by(MediaVersion.tags)
        ).all()
        remaining_tags = [v.tags for v in remaining]
        assert remaining_tags == ["ev-new", "sv-new"]
