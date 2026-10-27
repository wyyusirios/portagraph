package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import ru.portagraph.domain.Project;

import java.util.List;

public interface ProjectRepository extends JpaRepository<Project, Long> {

    /** Проекты, в которых пользователь является участником. */
    @Query("select p from Project p join p.members m where m.user.id = :userId and p.status = ru.portagraph.domain.ProjectStatus.ACTIVE order by p.createdAt desc")
    List<Project> findActiveForUser(Long userId);
}
