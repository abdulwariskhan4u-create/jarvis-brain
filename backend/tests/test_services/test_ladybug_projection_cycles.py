"""Exercise vector/graph mutations and reads together in the real native worker."""
import pytest


def test_reprojection_and_entity_relink_keep_native_worker_and_dense_recall_alive(tmp_path):
    pytest.importorskip('ladybug')
    from services.indexing.ladybug_worker import IsolatedLadybugStore
    from services.indexing.ladybug_store import EMBED_DIM
    store=IsolatedLadybugStore(str(tmp_path/'graph'),cooldown=0)
    pid=store.worker_pid
    try:
        for cycle in range(4):
            for i in range(24):
                vector=[0.0]*EMBED_DIM;vector[i]=1.0
                store.upsert_memory(record_id=f'm{i}',owner='QE',memory_type='procedural',
                    subject_scope='agent:QE',content=f'Capability lesson {i}',embedding=vector,
                    authority='agent_observed',confidence=.8,created_at=1,valid_from=1)
                for j in range(3):
                    name=f'Browser {j}'
                    store.link_entity(record_id=f'm{i}',entity_id=f'kg:QE:browser{j}',
                        name=name,etype='tool',normalized=name.lower())
                store.link_relations(record_id=f'm{i}',owner='QE',triples=[{
                    's':'QE','p':'tests','o':'Browser 0'}])
                hits=store.vector_search(owner='QE',query_embedding=vector,limit=1)
                assert hits and hits[0].record_id==f'm{i}', (cycle,i)
                store.query_anchored_memories(owner='QE',query='Browser 0')
                assert store.worker_pid==pid
        assert store.count()==24
    finally:
        store.close()
