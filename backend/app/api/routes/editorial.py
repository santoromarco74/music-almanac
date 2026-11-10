from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db

router = APIRouter(tags=["editorial"])
STATUSES = {"NEW", "TO_VERIFY", "READY", "IN_PROGRESS", "PUBLISHED", "DISCARDED"}
SCORE_FIELDS = {"historical_importance": 25, "artist_relevance": 20, "cultural_influence": 20, "discographic_interest": 15, "source_availability": 10, "narrative_potential": 10}
LINKS = {"artists": ("editorial_item_artists", "artist_id", "artists"), "releases": ("editorial_item_releases", "release_id", "releases"), "events": ("editorial_item_events", "event_id", "events")}

def one(db, sql, p=None):
    r = db.execute(text(sql), p or {}).mappings().first()
    return dict(r) if r else None

def many(db, sql, p=None):
    return [dict(r) for r in db.execute(text(sql), p or {}).mappings().all()]

def item_or_404(db, iid):
    x = one(db, "SELECT * FROM editorial_items WHERE id=:id", {"id": iid})
    if not x: raise HTTPException(404, "Scheda editoriale non trovata.")
    return x

def links_for(db, iid):
    return {k: many(db, f"SELECT {v[1]} AS id FROM {v[0]} WHERE editorial_item_id=:id", {"id": iid}) for k,v in LINKS.items()}

@router.get("/editorial-items")
def list_items(status: str | None = None, q: str | None = None, min_score: float | None = None, max_score: float | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    if status and status not in STATUSES: raise HTTPException(422, "Stato editoriale non valido.")
    return many(db, """SELECT i.*, s.total_score FROM editorial_items i LEFT JOIN LATERAL (SELECT total_score FROM editorial_scores WHERE editorial_item_id=i.id ORDER BY scored_at DESC LIMIT 1) s ON TRUE WHERE (CAST(:st AS TEXT) IS NULL OR i.status=CAST(:st AS editorial_status)) AND (CAST(:q AS TEXT) IS NULL OR i.title ILIKE '%'||:q||'%' OR i.summary ILIKE '%'||:q||'%') AND (CAST(:mn AS NUMERIC) IS NULL OR s.total_score>=:mn) AND (CAST(:mx AS NUMERIC) IS NULL OR s.total_score<=:mx) ORDER BY i.priority_score DESC NULLS LAST,i.created_at DESC OFFSET :o LIMIT :n""", {"st":status,"q":q,"mn":min_score,"mx":max_score,"o":offset,"n":limit})

@router.post("/editorial-items", status_code=201)
def create_item(payload: dict, db: Session = Depends(get_db)):
    title = str(payload.get("title") or "").strip()
    if not title: raise HTTPException(422, "title obbligatorio.")
    status = str(payload.get("status") or "NEW").upper()
    if status not in STATUSES or status == "PUBLISHED": raise HTTPException(422, "Una nuova scheda non può essere creata direttamente come PUBLISHED.")
    score = payload.get("priority_score")
    if score is not None and not 0 <= float(score) <= 100: raise HTTPException(422, "priority_score deve essere compreso tra 0 e 100.")
    x = one(db, "INSERT INTO editorial_items(title,summary,status,priority_score,article_url,notes) VALUES (:t,:s,CAST(:st AS editorial_status),:p,:u,:n) RETURNING *", {"t":title,"s":payload.get("summary"),"st":status,"p":score,"u":payload.get("article_url"),"n":payload.get("notes")})
    db.commit(); return x

@router.get("/editorial-items/{item_id}")
def get_item(item_id: UUID, db: Session = Depends(get_db)):
    x=item_or_404(db,item_id); x["links"]=links_for(db,item_id); x["tags"]=many(db,"SELECT t.* FROM editorial_tags t JOIN editorial_item_tags it ON it.editorial_tag_id=t.id WHERE it.editorial_item_id=:id ORDER BY t.name",{"id":item_id}); x["scores"]=many(db,"SELECT * FROM editorial_scores WHERE editorial_item_id=:id ORDER BY scored_at DESC",{"id":item_id}); return x

@router.patch("/editorial-items/{item_id}")
def update_item(item_id: UUID, payload: dict, db: Session = Depends(get_db)):
    old=item_or_404(db,item_id); allowed={"title","summary","priority_score","article_url","notes"}; c={k:v for k,v in payload.items() if k in allowed}
    if "title" in c:
        c["title"]=str(c["title"] or "").strip()
        if not c["title"]: raise HTTPException(422,"title non può essere vuoto.")
    if "priority_score" in c and c["priority_score"] is not None and not 0 <= float(c["priority_score"]) <= 100: raise HTTPException(422,"priority_score fuori intervallo.")
    if not c: return old
    x=one(db,"UPDATE editorial_items SET "+",".join(f"{k}=:{k}" for k in c)+",updated_at=now() WHERE id=:id RETURNING *",{**c,"id":item_id}); db.commit(); return x

@router.post("/editorial-items/{item_id}/status")
def change_status(item_id: UUID, payload: dict, db: Session = Depends(get_db)):
    x=item_or_404(db,item_id); target=str(payload.get("status") or "").upper()
    if target not in STATUSES: raise HTTPException(422,"Stato editoriale non valido.")
    transitions={"NEW":{"TO_VERIFY","DISCARDED"},"TO_VERIFY":{"READY","NEW","DISCARDED"},"READY":{"IN_PROGRESS","TO_VERIFY","DISCARDED"},"IN_PROGRESS":{"PUBLISHED","READY","DISCARDED"},"PUBLISHED":{"IN_PROGRESS"},"DISCARDED":{"NEW"}}
    if target not in transitions[x["status"]]: raise HTTPException(409,f"Transizione non consentita: {x['status']} → {target}.")
    if target == "PUBLISHED":
        if not x.get("summary") or len(x["summary"].strip()) < 40: raise HTTPException(422,"Per pubblicare è richiesto un summary di almeno 40 caratteri.")
        links=links_for(db,item_id)
        if not any(links.values()): raise HTTPException(422,"La scheda deve essere collegata ad almeno un artista, release o evento.")
        # Richiede almeno un collegamento documentale per una delle entità associate.
        predicates=[]; params={"id":item_id}
        for kind,(table,col,_) in LINKS.items(): predicates.append(f"EXISTS (SELECT 1 FROM {table} l JOIN entity_sources es ON es.{col}=l.{col} WHERE l.editorial_item_id=:id)")
        if not one(db,"SELECT EXISTS ("+" UNION ALL ".join("SELECT 1 WHERE "+p for p in predicates)+") AS ok",params)["ok"]: raise HTTPException(422,"Manca una fonte documentale associata alle entità della scheda.")
    x=one(db,"UPDATE editorial_items SET status=CAST(:st AS editorial_status),published_at=CASE WHEN :st='PUBLISHED' THEN now() WHEN :st<>'PUBLISHED' THEN NULL ELSE published_at END,updated_at=now() WHERE id=:id RETURNING *",{"st":target,"id":item_id}); db.commit(); return x

@router.put("/editorial-items/{item_id}/links/{kind}")
def set_links(item_id: UUID, kind: str, payload: dict, db: Session = Depends(get_db)):
    item_or_404(db,item_id)
    if kind not in LINKS: raise HTTPException(404,"Tipo di associazione non supportato.")
    table,col,target=LINKS[kind]; ids=payload.get("ids",[])
    if not isinstance(ids,list): raise HTTPException(422,"ids deve essere una lista.")
    try: ids=list(dict.fromkeys(UUID(str(v)) for v in ids))
    except ValueError as exc: raise HTTPException(422,"UUID non valido.") from exc
    if ids:
        found=one(db,f"SELECT count(*) AS n FROM {target} WHERE id = ANY(CAST(:ids AS UUID[]))",{"ids":ids})["n"]
        if found != len(ids): raise HTTPException(422,"Una o più entità non esistono.")
    db.execute(text(f"DELETE FROM {table} WHERE editorial_item_id=:id"),{"id":item_id})
    for eid in ids: db.execute(text(f"INSERT INTO {table}(editorial_item_id,{col}) VALUES (:i,:e)"),{"i":item_id,"e":eid})
    db.commit(); return {"kind":kind,"ids":ids}

@router.post("/editorial-items/{item_id}/scores", status_code=201)
def score_item(item_id: UUID, payload: dict, db: Session = Depends(get_db)):
    item_or_404(db,item_id); vals={k:float(payload.get(k,0)) for k in SCORE_FIELDS}
    for k,v in vals.items():
        if not 0 <= v <= SCORE_FIELDS[k]: raise HTTPException(422,f"{k} deve essere tra 0 e {SCORE_FIELDS[k]}.")
    total=round(sum(vals.values()),2)
    x=one(db,"INSERT INTO editorial_scores(editorial_item_id,historical_importance,artist_relevance,cultural_influence,discographic_interest,source_availability,narrative_potential,total_score,scoring_version) VALUES (:id,:historical_importance,:artist_relevance,:cultural_influence,:discographic_interest,:source_availability,:narrative_potential,:total,:version) RETURNING *",{"id":item_id,**vals,"total":total,"version":payload.get("scoring_version","v1")}); db.commit(); return x

@router.get("/editorial-tags")
def list_tags(db: Session=Depends(get_db)): return many(db,"SELECT * FROM editorial_tags ORDER BY name")
@router.post("/editorial-tags",status_code=201)
def create_tag(payload:dict,db:Session=Depends(get_db)):
    name=str(payload.get("name") or "").strip()
    if not name: raise HTTPException(422,"name obbligatorio.")
    try: x=one(db,"INSERT INTO editorial_tags(name) VALUES (:n) RETURNING *",{"n":name}); db.commit(); return x
    except IntegrityError as exc: db.rollback(); raise HTTPException(409,"Tag già esistente.") from exc
@router.put("/editorial-items/{item_id}/tags")
def set_tags(item_id:UUID,payload:dict,db:Session=Depends(get_db)):
    item_or_404(db,item_id); ids=payload.get("tag_ids",[])
    try: ids=list(dict.fromkeys(UUID(str(v)) for v in ids))
    except (ValueError,TypeError) as exc: raise HTTPException(422,"tag_ids non validi.") from exc
    db.execute(text("DELETE FROM editorial_item_tags WHERE editorial_item_id=:id"),{"id":item_id})
    for tid in ids: db.execute(text("INSERT INTO editorial_item_tags(editorial_item_id,editorial_tag_id) VALUES (:i,:t)"),{"i":item_id,"t":tid})
    try: db.commit()
    except IntegrityError as exc: db.rollback(); raise HTTPException(422,"Uno o più tag non esistono.") from exc
    return many(db,"SELECT t.* FROM editorial_tags t JOIN editorial_item_tags it ON it.editorial_tag_id=t.id WHERE it.editorial_item_id=:id ORDER BY t.name",{"id":item_id})

@router.delete("/editorial-items/{item_id}",status_code=204)
def delete_item(item_id:UUID,db:Session=Depends(get_db)):
    r=db.execute(text("DELETE FROM editorial_items WHERE id=:id"),{"id":item_id})
    if not r.rowcount: db.rollback(); raise HTTPException(404,"Scheda editoriale non trovata.")
    db.commit(); return Response(status_code=204)
