package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import ru.portagraph.domain.CodeChunk;

import java.util.List;

public interface CodeChunkRepository extends JpaRepository<CodeChunk, Long> {

    /**
     * Семантический поиск: ближайшие по косинусному расстоянию фрагменты проекта
     * (оператор {@code <=>} расширения pgvector). Фильтр по project_id обеспечивает
     * изоляцию кода разных клиентов.
     */
    @Query(value = """
            select c.* from code_chunks c
              join source_files f on f.id = c.source_file_id
              join git_repositories r on r.id = f.repository_id
             where r.project_id = :projectId
             order by c.embedding <=> cast(:query as vector)
             limit :limit
            """, nativeQuery = true)
    List<CodeChunk> findNearest(Long projectId, String query, int limit);

    @Modifying
    @Query("delete from CodeChunk c where c.sourceFile.id = :sourceFileId")
    void deleteBySourceFileId(Long sourceFileId);
}
